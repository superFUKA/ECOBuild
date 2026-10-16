"""CLIのログ：1回のコマンドで起きたことを、1行1件のJSON（JSON Lines）でファイルに残す（AIが読んで調べられるように）。

本体（ecobuild・ecowork・ecotask）は Python の logging で出すだけで、どこに書くかはここで決める。

置き場所は2つ：
- モジュールのログ（<モジュール>/.ecobuild/logs/）：そのモジュールで実行したコマンドのすべて。
  中に .gitignore（*）を置くので、gitには見えない。
- ECOBuildのログ（<ECOBUILD_HOME>/logs/）：モジュールの外で実行したコマンドのすべてと、
  モジュールで実行したコマンドの要約（どのモジュールのログに詳しく書いたか）。

量（log_level）：off・error・info・debug（既定。外部コマンドの引数・出力まで全部）。
ecobuild config set log_level <量>、1回だけなら環境変数 ECOBUILD_LOG_LEVEL。
大きさの上限（log_max_mb、既定 200）：置き場所ごとに、超えたら古い日のファイルから消す。

ログを書けなくても、コマンドは止めない（ログの失敗は黙って捨てる）。トークン等の秘密は伏せて書く。
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

LEVELS = {"off": logging.CRITICAL + 10, "error": logging.ERROR, "info": logging.INFO, "debug": logging.DEBUG}
DEFAULT_LEVEL = "debug"
DEFAULT_MAX_MB = 200
LEVEL_VARIABLE = "ECOBUILD_LOG_LEVEL"
MODULE_LOG_DIRECTORY = Path(".ecobuild") / "logs"

logger = logging.getLogger("ecobuild_cli")

# 秘密を伏せる：URLの中の認証情報、GitHubのトークン
_SECRETS = (
    (re.compile(r"(\b[a-z][a-z0-9+.-]*://)[^/\s@\"']+@", re.IGNORECASE), r"\1***@"),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"), "***"),
    (re.compile(r"((?:authorization|token)[\"']?\s*[:=]\s*[\"']?(?:bearer\s+|token\s+)?)[^\s\"',]+", re.IGNORECASE),
     r"\1***"),
)


def redact(text: str) -> str:
    for pattern, replacement in _SECRETS:
        text = pattern.sub(replacement, text)
    return text


def level_name() -> str:
    """ログの量。環境変数 ECOBUILD_LOG_LEVEL、なければ設定の log_level、なければ debug。"""
    value = os.environ.get(LEVEL_VARIABLE, "").strip().lower()
    if value in LEVELS:
        return value
    value = _config().get("log_level", "").strip().lower()
    return value if value in LEVELS else DEFAULT_LEVEL


def max_bytes() -> int:
    try:
        megabytes = int(_config().get("log_max_mb", DEFAULT_MAX_MB))
    except ValueError:
        megabytes = DEFAULT_MAX_MB
    return max(megabytes, 1) * 1024 * 1024


def _config() -> dict[str, str]:
    from ecobuild import settings
    try:
        return settings.load_config()
    except Exception:  # 設定が読めなくても、ログは既定で書く（設定の誤りはコマンドが知らせる）
        return {}


def global_directory() -> Path:
    from ecobuild import settings
    return settings.home() / "logs"


def module_directory(root: Path) -> Path:
    return Path(root) / MODULE_LOG_DIRECTORY


class _Handler(logging.Handler):
    """1回のコマンドのログ。対象のモジュールが分かるまでは手元にためておき、分かったらモジュールのログへ書く。
    最後までモジュールがなければ、ECOBuildのログへ書く。"""

    def __init__(self, run_id: str, level: int):
        super().__init__(level)
        self.run_id = run_id
        self.module_root: Path | None = None
        self.pending: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.write(self.line(record))
        except Exception:
            pass

    def handleError(self, record: logging.LogRecord) -> None:  # ログの失敗は表示しない
        pass

    def line(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "time": datetime.datetime.fromtimestamp(record.created).astimezone().isoformat(timespec="milliseconds"),
            "run": self.run_id,
            "level": record.levelname.lower(),
            "event": getattr(record, "event", "message"),
            "logger": record.name,
            "message": record.getMessage(),
        }
        data = getattr(record, "data", None)
        if data is not None:
            entry["data"] = data
        if record.exc_info:
            entry["traceback"] = logging.Formatter().formatException(record.exc_info)
        return redact(json.dumps(entry, ensure_ascii=False, default=_fallback))

    def write(self, line: str) -> None:
        if self.module_root is None:
            self.pending.append(line)
        elif not _append(module_directory(self.module_root), [line], module=True):
            # モジュールのフォルダーがなくなった（module delete 等）：ECOBuildのログへ
            _append(global_directory(), [line])

    def use_module(self, root: Path) -> None:
        if self.module_root is not None and Path(root) == self.module_root:
            return
        self.module_root = Path(root)
        lines, self.pending = self.pending, []
        if lines and not _append(module_directory(self.module_root), lines, module=True):
            _append(global_directory(), lines)

    def finish(self, summary: str) -> None:
        """終わり：モジュールがなければ、ためたものをECOBuildのログへ。あれば要約だけをECOBuildのログへ。"""
        if self.module_root is None:
            _append(global_directory(), self.pending)
            self.pending = []
        else:
            _append(global_directory(), [summary])


def _fallback(value: Any) -> Any:
    from ._output import to_data
    data = to_data(value)
    return data if data is not value else repr(value)


def _append(directory: Path, lines: list[str], *, module: bool = False) -> bool:
    """今日のファイル（YYYY-MM-DD.jsonl）に足す。書くたびに開いて閉じる（フォルダーを動かす操作を妨げない）。"""
    if not lines:
        return True
    if module and not (directory.parent.parent / "ecobuild.toml").is_file():
        return False
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if module:
            ignore = directory.parent / ".gitignore"
            if not ignore.exists():
                ignore.write_text("# ECOBuildのログ等（gitに見せない）\n*\n", encoding="utf-8", newline="\n")
        with open(directory / f"{datetime.date.today().isoformat()}.jsonl", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write("".join(line + "\n" for line in lines))
        return True
    except OSError:
        return not module


def prune(directory: Path, limit: int) -> None:
    """合計が上限を超えたら、古い日のファイルから消す（今日のファイルは残す）。"""
    try:
        files = sorted(directory.glob("*.jsonl"))
        total = sum(path.stat().st_size for path in files)
        today = f"{datetime.date.today().isoformat()}.jsonl"
        for path in files:
            if total <= limit or path.name == today:
                break
            total -= path.stat().st_size
            path.unlink()
    except OSError:
        pass


# 1回のコマンド -----------------------------------------------------------------

_current: _Handler | None = None
_started = 0.0
_command: dict[str, Any] = {}


def start(args: list[str]) -> None:
    """コマンドの始まり。ログの量が off なら何もしない。"""
    global _current, _started, _command
    name = level_name()
    if name == "off":
        return
    _started = time.monotonic()
    _current = _Handler(uuid.uuid4().hex[:12], LEVELS[name])
    root = logging.getLogger()
    root.addHandler(_current)
    root.setLevel(LEVELS[name])
    _install_process_hook()
    from importlib import metadata
    try:
        version = metadata.version("ecobuild")
    except metadata.PackageNotFoundError:
        version = None
    _command = {"args": list(args), "cwd": os.getcwd()}
    logger.info("ecobuild %s", " ".join(args), extra={"event": "command.start", "data": {
        **_command, "version": version, "python": sys.version.split()[0], "platform": sys.platform,
        "pid": os.getpid(), "level": name}})


def use_module(root: Path) -> None:
    """対象のモジュールが分かった。ここからのログ（それまでのものも）はモジュールのログへ。"""
    if _current is not None:
        _current.use_module(root)


def finish(exit_code: int | None) -> None:
    """コマンドの終わり。終了コードと所要時間を書き、ログのファイルを閉じる。"""
    global _current
    handler = _current
    if handler is None:
        return
    data = {"exit_code": exit_code, "seconds": round(time.monotonic() - _started, 3)}
    level = logging.INFO if exit_code in (0, None) else logging.ERROR
    logger.log(level, "終了コード %s", exit_code, extra={"event": "command.end", "data": data})
    _current = None
    logging.getLogger().removeHandler(handler)
    summary = handler.line(logging.LogRecord(logger.name, level, "", 0, "ecobuild %s", (" ".join(_command["args"]),),
                                             None))
    entry = json.loads(summary)
    entry.update(event="command.summary", data={
        **_command, **data, "module": handler.module_root.as_posix() if handler.module_root else None,
        "log": module_directory(handler.module_root).as_posix() if handler.module_root else None})
    try:
        handler.finish(redact(json.dumps(entry, ensure_ascii=False)))
        limit = max_bytes()
        prune(global_directory(), limit)
        if handler.module_root is not None:
            prune(module_directory(handler.module_root), limit)
    except Exception:
        pass


# 外部コマンド（CppBuild の CMake・MSBuild 等、ecotask.process を通らないもの）--------------------

_hook_installed = False


def _install_process_hook() -> None:
    """プロセスの起動（subprocess.Popen の監査イベント）を書く。監査フックは外せないので、1回だけ入れる。"""
    global _hook_installed
    if not _hook_installed:
        sys.addaudithook(_audit)
        _hook_installed = True


def _audit(event: str, arguments: tuple) -> None:
    if event != "subprocess.Popen" or _current is None:
        return
    try:
        if _from_process_module():
            return  # ecotask.process が、終了コード・出力と一緒に書く
        executable, args, cwd, _env = arguments
        args = [args] if isinstance(args, (str, bytes)) else list(args or ())
        logger.debug("%s", " ".join(map(str, args)), extra={"event": "process.start", "data": {
            "args": [str(a) for a in args], "executable": None if executable is None else str(executable),
            "cwd": None if cwd is None else str(cwd), "caller": _caller()}})
    except Exception:
        pass


def _from_process_module() -> bool:
    frame = sys._getframe(2)
    while frame is not None:
        if frame.f_globals.get("__name__") == "ecotask.process":
            return True
        frame = frame.f_back
    return False


def _caller() -> str | None:
    """起動したコード（subprocess・logging 以外で最も近いもの）。"""
    frame = sys._getframe(3)
    while frame is not None:
        name = frame.f_globals.get("__name__", "")
        if name not in ("subprocess", __name__) and not name.startswith("logging"):
            return f"{name}:{frame.f_lineno}"
        frame = frame.f_back
    return None
