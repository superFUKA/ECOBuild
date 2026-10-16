"""外部コマンド（git・gh等）の実行。出力はUTF-8として取り込む。

実行したコマンド・終了コード・出力・所要時間を logging（DEBUG）で出す。どこに書くかは使う側（CLI）が決める。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
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


def run(
    args: list[str] | tuple[str, ...],
    *,
    cwd: Path | str | None = None,
    check: bool = True,
    input: str | None = None,
    env: dict[str, str] | None = None,
) -> Completed:
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
    if check and not completed.ok:
        raise ProcessFailed(completed)
    return completed
