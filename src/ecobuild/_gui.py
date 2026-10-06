"""TortoiseGit による履歴・差分の表示（Windows・任意。I-013）。"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .errors import EcoBuildError, ErrorCode


def find() -> str | None:
    """TortoiseGitProc の場所。なければNone。"""
    found = shutil.which("TortoiseGitProc")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432")):
        if base:
            candidate = Path(base) / "TortoiseGit" / "bin" / "TortoiseGitProc.exe"
            if candidate.is_file():
                return str(candidate)
    return None


def open_window(command: str, path: Path, **extra: str) -> None:
    """TortoiseGitの画面を開く（終わるのを待たない）。"""
    tool = find()
    if tool is None:
        raise EcoBuildError(ErrorCode.TOOL_MISSING, "TortoiseGit が見つかりません。",
                            hint="TortoiseGit をインストールするか、--gui を付けずに実行してください（文字で表示します）。")
    args = [tool, f"/command:{command}", f"/path:{path}"] + [f"/{key}:{value}" for key, value in extra.items()]
    subprocess.Popen(args, cwd=path if path.is_dir() else path.parent)
