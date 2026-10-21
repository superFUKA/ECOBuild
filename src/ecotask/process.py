"""外部コマンド（git・gh等）の実行。出力はUTF-8として取り込む。ecotask・ecowork と、ecowork.process を通して ecobuild も使う。

実行したコマンド・終了コード・出力・所要時間を logging（DEBUG）で出す。どこに書くかは使う側（CLI）が決める。
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .errors import ErrorCode, TaskError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Completed:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def output(self) -> str:
        return "\n".join(part for part in (self.stdout.strip(), self.stderr.strip()) if part)


class ProcessFailed(Exception):
    """終了コードが0以外だった。呼び出し側が作業のエラーへ変換する。"""

    def __init__(self, completed: Completed):
        super().__init__(completed.output)
        self.completed = completed


def find_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise TaskError(
            ErrorCode.TOOL_MISSING,
            f"{name} が見つかりません。",
            hint=f"{name} をインストールし、PATHから実行できるようにしてください。",
        )
    return path


def secret_output(args: list[str] | tuple[str, ...]) -> str | None:
    """出力が秘密（gh auth token のトークン）のコマンドを実行し、標準出力を返す（失敗なら None）。
    ログには、実行したことと終了コードだけを書く（出力は書かない）。"""
    process = subprocess.run([find_tool(args[0]), *args[1:]], capture_output=True, text=True, encoding="utf-8",
                             errors="replace")
    logger.debug("%s", " ".join(args), extra={"event": "process", "data": {
        "args": list(args), "returncode": process.returncode, "stdout": "（秘密のため書かない）"}})
    return process.stdout.strip() if process.returncode == 0 and process.stdout.strip() else None


# GitHub・ネットワークの一時的な失敗（502 等）は、少し待ってやり直す。やり直すのは、繰り返しても結果が同じ操作だけ
# （読むだけの gh・git の fetch / ls-remote / clone / push）。作る操作（gh issue create 等）は、失敗に見えて実は
# できていることがあり、やり直すと二重になるのでやり直さない。
RETRY_WAITS = (2.0, 5.0)   # やり直す前に待つ秒数（回数はこの数）
TRANSIENT = re.compile(r"HTTP 5\d\d|Bad Gateway|Service Unavailable|Gateway Time-?out|secondary rate limit|"
                       r"returned error: 5\d\d|Could not resolve host|Connection (?:timed out|reset|refused)|"
                       r"Operation timed out|RPC failed|early EOF|TLS handshake|unexpected disconnect|"
                       r"cannot lock ref|Unable to create '[^']*\.lock'", re.IGNORECASE)   # 同じ clone の fetch が同時に走った
_GH_READS = frozenset({"view", "list", "status", "diff", "checks"})
_GIT_REPEATABLE = frozenset({"fetch", "ls-remote", "clone", "push"})


def repeatable(args: list[str] | tuple[str, ...]) -> bool:
    """失敗したときにやり直してよい操作か（繰り返しても結果が同じ）。"""
    words = [str(a) for a in args]
    if words[:1] == ["gh"]:
        if words[1:2] == ["api"]:
            method = next((words[i + 1] for i, w in enumerate(words) if w in ("--method", "-X") and i + 1 < len(words)), "GET")
            return method.upper() == "GET" and not any(w in ("-f", "-F", "--field", "--raw-field", "--input") for w in words)
        return len(words) > 2 and words[2] in _GH_READS
    if words[:1] == ["git"]:
        rest = [w for i, w in enumerate(words[1:], 1) if not (w == "-c" or words[i - 1] == "-c")]
        return bool(rest) and rest[0] in _GIT_REPEATABLE
    return False


def run(
    args: list[str] | tuple[str, ...],
    *,
    cwd: Path | str | None = None,
    check: bool = True,
    input: str | None = None,
    env: dict[str, str] | None = None,
    wait: Callable[[float], None] = time.sleep,
) -> Completed:
    """args を実行する。一時的な失敗は、やり直してよい操作だけ RETRY_WAITS のとおり待ってやり直す。"""
    waits = list(RETRY_WAITS) if repeatable(args) else []
    while True:
        completed = _run_once(args, cwd=cwd, input=input, env=env)
        if completed.ok or not waits or not TRANSIENT.search(completed.stderr or ""):
            break
        logger.info("一時的な失敗のため、やり直します：%s", " ".join(args[:3]), extra={"event": "process.retry"})
        wait(waits.pop(0))
    if check and not completed.ok:
        raise ProcessFailed(completed)
    return completed


def _run_once(args, *, cwd, input, env) -> Completed:
    tool = find_tool(args[0])
    merged_env = None if env is None else {**os.environ, **env}
    started = time.monotonic()
    process = subprocess.run(
        [tool, *args[1:]],
        cwd=cwd,
        input=input,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=merged_env,
    )
    completed = Completed(tuple(args), process.returncode, process.stdout, process.stderr)
    if logger.isEnabledFor(logging.DEBUG):
        # 標準入力・環境変数の値は秘密（gh secret set の値、トークン）を含みうるので書かない
        logger.debug("%s", " ".join(args), extra={"event": "process", "data": {
            "args": list(args), "executable": tool, "cwd": None if cwd is None else str(cwd),
            "env": sorted(env or ()), "input_chars": None if input is None else len(input),
            "returncode": process.returncode, "seconds": round(time.monotonic() - started, 3),
            "stdout": process.stdout, "stderr": process.stderr}})
    return completed
