import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

GIT_ENV = {
    "GIT_AUTHOR_NAME": "ECOBuild Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "ECOBuild Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, **GIT_ENV},
    ).stdout.strip()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def remove_tree(path: Path) -> None:
    """gitの読み取り専用ファイル（Windows）も含めて削除する。"""

    def make_writable(function, target, _):
        os.chmod(target, stat.S_IWRITE)
        function(target)

    shutil.rmtree(path, onexc=make_writable)


def short_temporary_directory() -> Path:
    """Windowsのパス長の制限を避けるため、短い一時ディレクトリを作る。"""
    return Path(tempfile.mkdtemp(prefix="eb"))
