import os
import subprocess
from pathlib import Path

import pytest

GIT_ENV = {
    "GIT_AUTHOR_NAME": "ECOBuild Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "ECOBuild Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch):
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, **GIT_ENV},
    ).stdout.strip()


@pytest.fixture
def remote_and_clone(tmp_path):
    """mainに初回コミットがある空のリモート（bare）と、その作業用のclone。"""
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    work = tmp_path / "work"
    git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", str(remote))
    git(tmp_path, "init", "--quiet", "--initial-branch=main", str(seed))
    (seed / "README.md").write_text("seed\n", encoding="utf-8")
    git(seed, "add", "README.md")
    git(seed, "commit", "--quiet", "-m", "init")
    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "--quiet", "origin", "main")
    git(tmp_path, "clone", "--quiet", str(remote), str(work))
    return remote, work


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
