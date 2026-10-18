"""エージェントを新しい端末の画面で起動する。起動したら待たずに戻る（エージェントは別の画面で動き続ける）。

Windows は新しいコンソール。ほかは x-terminal-emulator（Debian 系の既定の端末）か、環境変数 TERMINAL の端末。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .errors import AgentError, ErrorCode

logger = logging.getLogger(__name__)

DEFAULT_COMMAND = ("claude",)


@dataclass(frozen=True)
class Session:
    """起動したエージェント。pid は画面を開いたプロセス（Windows ではエージェントそのもの）。"""
    pid: int
    command: tuple[str, ...]
    directory: Path


def start(directory: Path | str, command: list[str] | tuple[str, ...] = DEFAULT_COMMAND,
          env: dict[str, str] | None = None) -> Session:
    """directory を作業ディレクトリにして、command を新しい端末の画面で起動する。env：起動する環境（既定はこのプロセスの）。"""
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise AgentError(ErrorCode.DIRECTORY_NOT_FOUND, f"フォルダーが見つかりません：{directory}")
    if not command:
        raise AgentError(ErrorCode.AGENT_NOT_FOUND, "起動するエージェントのコマンドが空です。")
    program = shutil.which(command[0])
    if program is None:
        raise AgentError(ErrorCode.AGENT_NOT_FOUND, f"エージェント {command[0]} が見つかりません。",
                         hint=f"{command[0]} をインストールし、PATH から実行できるようにしてください。")
    args = [program, *command[1:]]
    try:
        if sys.platform == "win32":
            process = subprocess.Popen(args, cwd=directory, env=env, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            process = subprocess.Popen([_terminal(), "-e", *args], cwd=directory, env=env, start_new_session=True,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as error:
        raise AgentError(ErrorCode.LAUNCH_FAILED, f"エージェントを起動できませんでした：{error}") from error
    logger.debug("agent started", extra={"data": {"pid": process.pid, "args": args, "cwd": str(directory)}})
    return Session(process.pid, tuple(command), directory)


def _terminal() -> str:
    for name in (os.environ.get("TERMINAL"), "x-terminal-emulator"):
        if name and (path := shutil.which(name)):
            return path
    raise AgentError(ErrorCode.NO_TERMINAL, "新しい画面を開く端末が見つかりません。",
                     hint="環境変数 TERMINAL に端末のコマンド（-e で実行するコマンドを受け取るもの）を設定してください。")
