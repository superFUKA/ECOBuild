"""worktree の作業空間を、本物の docker の中の git で読む（ecobuild_container.layout の付け方）。
docker が使えて、このPCの git が 2.48 以上の所だけ（相対パスで記録した worktree を作る）。中の git は 2.48 以上のイメージ。"""

import subprocess

import pytest

import ecobuild_container as container
from ecobuild_container import docker
from ecowork.git import MINIMUM_VERSION, git_version
from helpers import git

REAL_RUN = docker.run   # conftest の _no_docker が試験の間は偽物にするので、先に取っておく
IMAGE = "alpine/git:v2.52.0"   # 中の git（2.48 以上。entrypoint は git）


@pytest.fixture
def real_docker():
    if git_version() < MINIMUM_VERSION:
        pytest.skip("このPCの git が 2.48 未満です")
    found = docker.status(REAL_RUN)
    if not found.ready:
        pytest.skip(f"Docker が使えません（{found.detail}）")
    return found.command


def test_the_git_inside_reads_a_relative_worktree(tmp_path, real_docker):
    """元の .git と作業空間だけを同じ並びで付ければ、中の git が相対パスの記録をたどれる（status・log・commit）。
    元の clone の作業ツリー（未コミットのファイル）は中から見えない。"""
    main = tmp_path / "Calc"
    git(tmp_path, "init", "--quiet", "--initial-branch=main", str(main))
    (main / "README.md").write_text("calc\n", encoding="utf-8")
    git(main, "add", "README.md")
    git(main, "commit", "--quiet", "-m", "init")
    (main / "secret.txt").write_text("元の clone だけのもの\n", encoding="utf-8")
    place = main / ".ecobuild" / "w" / "3"
    git(main, "worktree", "add", "--quiet", "--relative-paths", "-b", "task/3-x", str(place))
    assert not (place / ".git").read_text(encoding="utf-8").split(":", 1)[1].strip().startswith(("/", "C:", "c:"))

    shown = container.layout(place)
    assert shown.workdir == "/repo/.ecobuild/w/3"
    owned = container.own_drive(place, REAL_RUN, real_docker)
    volumes = [item for outer, inner in shown.mounts
               for item in ("--volume", f"{container.mount_path(outer, real_docker, owned=owned)}:{inner}")]

    def inside(*args):
        done = REAL_RUN([*real_docker, "run", "--rm", "--user", container.USER, *volumes, "--workdir", shown.workdir,
                         "--env", "GIT_AUTHOR_NAME=t", "--env", "GIT_AUTHOR_EMAIL=t@example.com",
                         "--env", "GIT_COMMITTER_NAME=t", "--env", "GIT_COMMITTER_EMAIL=t@example.com",
                         IMAGE, "-c", "safe.directory=*", "-C", shown.workdir, *args])
        assert done.ok, done.output
        return done.output

    assert "## task/3-x" in inside("status", "--porcelain=v1", "--branch")
    assert "init" in inside("log", "--oneline", "-1")
    assert "secret.txt" not in inside("ls-files", "--others")   # 中の作業空間には元の clone のファイルがない
    (place / "a.txt").write_text("a\n", encoding="utf-8")
    inside("add", "a.txt")
    inside("commit", "--quiet", "-m", "inside")
    assert git(main, "log", "--oneline", "-1", "task/3-x").endswith("inside")   # このPCの側から見える
    listed = subprocess.run(["git", "-C", str(main), "worktree", "list", "--porcelain"], capture_output=True,
                            text=True, check=True).stdout
    assert "prunable" not in listed and "task/3-x" in listed                  # このPCの worktree の記録は壊れない
