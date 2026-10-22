"""作業空間のロック：使っている最中の作業空間で、ブランチが入れ替わったり（切り替え）、タスクブランチが消されたりしないようにする。

理由はどれか1つでもあればロック中：
- manual：workspace lock で付け、workspace unlock で外す（外すまで残る）。
- agent・container・command：自動。原因（エージェントのプロセス・コンテナ・実行中のコマンド）が終われば外れる。
  workspace unlock では外れない。agent・container は拡張（ecobuild_agent・ecobuild_container）が知っているので、
  拡張が add_source で判断の口を足す（本体は拡張を知らない。つなぐのは ecobuild_bundle）。command は本体が持つ。
- 非常用の force（workspace unlock --force）：その時にある自動ロックを、その原因（key。プロセスの pid・コンテナの id 等）が
  続く間だけ無視する。原因が終わって別の原因ができれば、また止まる。

手動のロック・force・実行中のコマンドは、作業空間の .ecobuild/lock.json に持つ。コミットしないよう、書くときに
.git/info/exclude に足す（以前に作ったモジュールの .ecobuild/.gitignore を変えずに済む）。読んで書き直す間は
fsutil.locked で1つずつにする。
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import config as _config
from .fsutil import locked, process_alive

FILE_NAME = f"{_config.DIRECTORY}/lock.json"
LOCK_NAME = f"{_config.DIRECTORY}/lock.lock"   # lock.json を読んで書き直す間のロック

MANUAL, AGENT, CONTAINER, COMMAND = "manual", "agent", "container", "command"
AUTOMATIC = (AGENT, CONTAINER, COMMAND)

# ブランチが変わると困るので、実行中はロックにするコマンド（ビルド・テスト・実行・確認〔task submit は中で check を行う〕：
# 手元のファイルとブランチの版が合っている前提で長く動く。ほかは短いので対象にしない）
COMMANDS = ("build", "clean", "rebuild", "test", "run", "check", "task submit")


@dataclass(frozen=True)
class Reason:
    """ロックの理由。JSON の形はこのまま（GUI と合わせた約束）。"""
    kind: str                  # manual・agent・container・command
    text: str                  # 日本語の説明
    since: str | None = None   # ISO 時刻
    pid: int | None = None


@dataclass(frozen=True)
class Lock:
    locked: bool
    reasons: tuple[Reason, ...] = ()


# 拡張の判断：作業空間の一覧 → それぞれの (理由, key) の一覧（同じ順）。key は原因を表す印（force が覚える）。
# docker のように1回で全部を調べたほうが軽いものがあるので、まとめて受け取る
Detected = tuple[Reason, str]
Source = Callable[[Sequence[Path]], list[list[Detected]]]
_sources: list[Source] = []


def add_source(source: Source) -> None:
    """自動のロックの理由を調べる口を足す（同じものを2回足しても1つ）。"""
    if source not in _sources:
        _sources.append(source)


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _file(root: Path) -> Path:
    return Path(root) / FILE_NAME


def _changing(root: Path):
    _exclude(root)
    return locked(Path(root) / LOCK_NAME, timeout=10)


def _read(root: Path) -> dict:
    try:
        data = json.loads(_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(root: Path, data: dict) -> None:
    path = _file(root)
    if not (data.get("manual") or data.get("force") or data.get("commands")):
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _exclude(root)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for attempt in range(5):   # Windows：他のコマンドが読んでいる間は置き換えられない
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                temporary.unlink(missing_ok=True)
                raise
            time.sleep(0.05)


def _exclude(root: Path) -> None:
    """lock.json・lock.lock を git の除外（.git/info/exclude）に足す（まだなければ）。"""
    exclude(root, f"/{FILE_NAME}", f"/{LOCK_NAME}")


def exclude(root: Path, *wanted: str) -> None:
    """wanted の行を git の除外（共通の .git/info/exclude。作業空間どうしで共有）に足す（まだなければ）。"""
    path = _git_common_directory(Path(root)) / "info" / "exclude"
    if not path.parent.is_dir():
        return
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        missing = [line for line in wanted if line not in text.splitlines()]
        if missing:
            path.write_text(text + ("" if not text or text.endswith("\n") else "\n") + "\n".join(missing) + "\n",
                               encoding="utf-8", newline="\n")
    except OSError:
        pass


def _git_common_directory(root: Path) -> Path:
    """root の git の置き場所（info/exclude がある所）。git worktree・サブモジュールでは .git がファイル（gitdir: …）で、
    除外は本体の置き場所（commondir）にある。git を呼ばずにファイルから読む（ロックは頻繁に読むので軽く）。"""
    dot = root / ".git"
    if not dot.is_file():
        return dot
    try:
        text = dot.read_text(encoding="utf-8").strip()
        directory = Path(text.removeprefix("gitdir:").strip())
        directory = directory if directory.is_absolute() else root / directory
        common = directory / "commondir"
        if common.is_file():
            shared = Path(common.read_text(encoding="utf-8").strip())
            return shared if shared.is_absolute() else directory / shared
        return directory
    except OSError:
        return dot


def _live_commands(data: dict) -> list[dict]:
    return [c for c in data.get("commands", []) if isinstance(c, dict) and isinstance(c.get("pid"), int)
            and process_alive(c["pid"])]


# 手動 -------------------------------------------------------------------------------------

def lock(root: Path, reason: str = "") -> None:
    """手動のロックを付ける（既に付いていれば理由と時刻を更新）。"""
    with _changing(root):
        data = _read(root)
        data["manual"] = {"reason": reason, "since": now()}
        _write(root, data)


def unlock(root: Path, *, force: bool = False) -> None:
    """手動のロックを外す。force：今ある自動ロックも、その原因が続く間だけ無視させる。"""
    ignore = [key for reasons in detect([root]) for _, key in reasons] if force else []
    with _changing(root):
        data = _read(root)
        data.pop("manual", None)
        if force:
            data["force"] = sorted(set(data.get("force", [])) | set(ignore))
        _write(root, data)


# コマンドの実行中 ---------------------------------------------------------------------------

@contextmanager
def running(root: Path, command: str) -> Iterator[None]:
    """コマンドを実行している間、その作業空間をロックする（command）。書けなくても（読み取り専用等）コマンドは止めない。"""
    token = uuid.uuid4().hex
    try:
        with _changing(root):
            data = _read(root)
            data["commands"] = _live_commands(data) + [{"id": token, "pid": os.getpid(), "command": command,
                                                        "since": now()}]
            _write(root, data)
        registered = True
    except OSError:
        registered = False
    try:
        yield
    finally:
        if registered:
            try:
                with _changing(root):
                    data = _read(root)
                    data["commands"] = [c for c in _live_commands(data) if c.get("id") != token]
                    _write(root, data)
            except OSError:
                pass


# 調べる -------------------------------------------------------------------------------------

def detect(roots: Sequence[Path]) -> list[list[Detected]]:
    """作業空間ごとの、今ある理由（force で無視されるものも含む）と、その原因の印。"""
    found: list[list[Detected]] = [[] for _ in roots]
    for index, root in enumerate(roots):
        data = _read(root)
        manual = data.get("manual")
        if isinstance(manual, dict):
            reason = str(manual.get("reason") or "")
            found[index].append((Reason(MANUAL, "手動でロックされています" + (f"（{reason}）" if reason else ""),
                                        manual.get("since") if isinstance(manual.get("since"), str) else None),
                                 "manual"))
        for item in _live_commands(data):
            pid = item["pid"]
            found[index].append((Reason(COMMAND, f"ecobuild {item.get('command', '')} を実行中です（pid {pid}）",
                                        item.get("since") if isinstance(item.get("since"), str) else None, pid),
                                 f"command:{pid}:{item.get('id', '')}"))
    for source in _sources:
        for index, reasons in enumerate(source(roots)):
            found[index] += reasons
    return found


def status_of(roots: Sequence[Path]) -> list[Lock]:
    """作業空間ごとのロックの状態（force で無視中の自動ロックは除く。まとめて調べる）。"""
    result = []
    for root, reasons in zip(roots, detect(roots)):
        ignored = set(_read(root).get("force", []))
        kept = tuple(reason for reason, key in reasons if key not in ignored or reason.kind == MANUAL)
        result.append(Lock(bool(kept), kept))
    return result


def status(root: Path) -> Lock:
    return status_of([Path(root)])[0]
