import shutil
import sys

import pytest

from helpers import GIT_ENV, git


def pytest_collection_modifyitems(config, items):
    """本物の CppBuild の試験（cppbuild）は、C++ のビルドの道具がない環境（エージェントのコンテナ等）では飛ばす。
    Windows では CppBuild が Visual Studio の Ninja・コンパイラを探すので、ほかの OS だけ PATH で確かめる。"""
    missing = [] if sys.platform == "win32" else [tool for tool in ("cmake", "ninja", "c++") if shutil.which(tool) is None]
    if missing:
        skip = pytest.mark.skip(reason="C++ のビルドの道具がありません：" + "、".join(missing))
        for item in items:
            if "cppbuild" in item.keywords:
                item.add_marker(skip)


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch):
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture(autouse=True)
def _tool_home(monkeypatch, tmp_path_factory):
    """ツールの設定とcloneの記録は試験ごとの場所に（このPCの本物を読み書きしない）。"""
    monkeypatch.setenv("ECOBUILD_HOME", str(tmp_path_factory.mktemp("ecobuild-home")))


@pytest.fixture(autouse=True)
def _outside_agents(monkeypatch):
    """ECOBuild の作業空間（エージェントの窓・コンテナの中）で試験を動かしても、その印で動きを変えない。"""
    from ecobuild_agent import team
    from ecobuild_container import INSIDE
    monkeypatch.delenv(team.WINDOW_VARIABLE, raising=False)
    monkeypatch.delenv(INSIDE, raising=False)


@pytest.fixture(autouse=True)
def _no_docker(monkeypatch):
    """Docker の診断（doctor）は、このPCの本物の wsl・docker を呼ばない（使えないものとして答える）。"""
    from ecobuild_container import docker
    monkeypatch.setattr(docker, "run", lambda args: docker.Completed(tuple(args), 1, ""))


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


@pytest.fixture
def module(remote_and_clone, tmp_path):
    """CppBuildを使わない、gitだけのモジュール（ブランチ・タスクブランチの試験用）。"""
    from ecobuild import config
    from ecobuild_bundle import Module
    from fakes import FakeGitHub

    remote, work = remote_and_clone
    config.save(config.ModuleConfig.for_new_module("Calc", "cpp"), work / config.FILE_NAME)
    git(work, "add", config.FILE_NAME)
    git(work, "commit", "--quiet", "-m", "設定")
    git(work, "push", "--quiet", "origin", "main")
    github = FakeGitHub(tmp_path / "gh")
    github.use_bare(remote)
    return Module.find(work, github=github)


@pytest.fixture
def repository(remote_and_clone, tmp_path):
    """ecoworkのリポジトリ（偽のGitHub＋手元のbare）。CLIのコマンド名は ecobuild とする。"""
    from ecowork import Repository
    from fakes import FakeGitHub

    remote, work = remote_and_clone
    github = FakeGitHub(tmp_path / "gh")
    github.use_bare(remote)
    return Repository(work, github=github, command="ecobuild")
