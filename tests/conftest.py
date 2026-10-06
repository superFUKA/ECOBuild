import pytest

from helpers import GIT_ENV, git


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch):
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)


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
    """CppBuildを使わない、gitだけのモジュール（ブランチ・作業空間の試験用）。"""
    from ecobuild import config
    from ecobuild.module import Module
    from fakes import FakeGitHub

    remote, work = remote_and_clone
    config.save(config.ModuleConfig.for_new_module("Calc", app=False), work / config.FILE_NAME)
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
