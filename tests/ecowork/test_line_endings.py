"""改行コード：clone の扱いを決める・改行コードだけの差を見分けて、task commit が既定で含めない。"""

import subprocess

import pytest

from helpers import git, write
from ecowork import git as _git
from ecowork.git import Git

pytestmark = pytest.mark.local


def _flip_line_endings(root, name):
    """name を、記録（HEAD）と改行コードだけが違う中身にする（改行を変換しない git で見る）。"""
    git(root, "config", "core.autocrlf", "false")
    recorded = subprocess.run(["git", "show", f"HEAD:{name}"], cwd=root, capture_output=True, check=True).stdout
    flipped = recorded.replace(b"\r\n", b"\n") if b"\r\n" in recorded else recorded.replace(b"\n", b"\r\n")
    (root / name).write_bytes(flipped)


def test_clone_takes_out_files_as_recorded(remote_and_clone, tmp_path):
    remote, _ = remote_and_clone
    cloned = _git.clone(str(remote), tmp_path / "cloned")
    assert cloned.get_config("core.autocrlf") == "input"


def test_eol_only_changes_are_told_apart(remote_and_clone):
    _, work = remote_and_clone
    _flip_line_endings(work, "README.md")
    write(work / "b.txt", "b\n")
    git(work, "add", "b.txt")
    repo = Git(work)
    assert repo.eol_only("HEAD") == ("README.md",)
    write(work / "README.md", "changed\r\n")   # 中身も変われば、改行だけの差ではない
    assert repo.eol_only("HEAD") == ()


def test_status_and_commit_leave_out_eol_only_changes(repository):
    root = repository.root
    task_branch = repository.create_task("改行").start()
    _flip_line_endings(root, "README.md")
    write(root / "a.txt", "a\n")
    git(root, "add", "a.txt")
    write(root / "a.txt", "a2\n")
    assert repository.status().eol_only == ("README.md",)
    result = task_branch.record("a を足す")
    assert result.files == ("a.txt",) and result.eol_only == ("README.md",)
    assert "README.md" in repository.git.working_tree().unstaged   # 消さずに残す
    named = task_branch.record("改行も", ("README.md",))           # 名前を書けば含める
    assert named.files == ("README.md",) and named.eol_only == ()
