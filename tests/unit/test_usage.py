"""作業空間を使っている最中か（ecobuild.usage）：コマンドの実行中・エージェント。消す・切り替える直前に確かめるだけ
（以前のロック〔手動・--force・コンテナが動いている間〕はなくした）。"""

import json
import os
import subprocess
import sys

import pytest

from fake_docker import FakeDocker
import ecobuild_bundle  # noqa: F401（拡張の口〔動いているエージェント〕をつなぐ）
import ecobuild_container as container
from ecobuild import config, usage
from ecobuild_agent import status
from ecobuild_container import docker


@pytest.fixture
def root(tmp_path):
    folder = tmp_path / "ws"
    (folder / config.DIRECTORY).mkdir(parents=True)
    return folder


def dead_pid():
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def test_a_command_makes_it_in_use_only_while_running(root):
    with usage.running(root, "build"):
        texts = usage.reasons(root)
        assert len(texts) == 1 and "build" in texts[0] and str(os.getpid()) in texts[0]
        with usage.running(root, "test"):
            assert len(usage.reasons(root)) == 2
        assert len(usage.reasons(root)) == 1
    assert usage.reasons(root) == [] and not (root / usage.FILE_NAME).exists()


def test_a_command_of_a_dead_process_is_not_in_use(root):
    data = {"commands": [{"id": "x", "pid": dead_pid(), "command": "build"}]}
    (root / usage.FILE_NAME).write_text(json.dumps(data), encoding="utf-8")
    assert usage.reasons(root) == []


def test_a_running_agent_makes_it_in_use(root):
    """作業空間のエージェントの誰か1人でも動いていれば使用中（エージェントごとの running.json）。"""
    from ecobuild_agent import agents
    first = agents.create(registration="worker", workspace=root)
    helper = agents.create(registration="worker", workspace=root, kind=agents.HELPER, parent=first.id)
    folder = status.prepare(first.folder, root)
    assert usage.reasons(root) == []
    status.started(folder, os.getpid())
    assert len(usage.reasons(root)) == 1 and first.id in usage.reasons(root)[0]
    status.started(folder, os.getpid(), status.APP)
    assert "係" in usage.reasons(root)[0]
    status.started(folder, dead_pid())
    assert usage.reasons(root) == []
    status.started(helper.folder, os.getpid())                           # 手伝いだけが動いていても
    assert len(usage.reasons(root)) == 1
    status.started(helper.folder, dead_pid())
    assert usage.reasons(root) == []


def test_a_running_container_is_not_in_use_and_docker_is_not_called(tmp_path, monkeypatch):
    """コンテナが動いているだけでは使用中にしない。確かめるときに docker（Windows では WSL）を呼ばない。"""
    fake = FakeDocker(monkeypatch)
    monkeypatch.setattr(docker, "run", fake.run)
    monkeypatch.setattr(docker, "probe", fake.run)
    roots = []
    for index in range(2):
        folder = tmp_path / f"w{index}"
        (folder / config.DIRECTORY).mkdir(parents=True)
        container.choose(folder, True, fake.run)
        fake.containers[container.name(folder)] = ["running", "image", "1"]
        roots.append(folder)
    fake.calls.clear()
    assert usage.reasons_of(roots) == [[], []]
    assert fake.calls == []


def test_commands_inside_the_container_do_not_write(root, monkeypatch):
    """コンテナの中の ecobuild は running.json に書かない（中の pid はこのPCでは確かめられず、このPCの記録を消してしまう）。
    渡しているこのPCの CLI が書く（_inside.route）。"""
    from types import SimpleNamespace
    from ecobuild_cli._output import Invocation

    held = SimpleNamespace(root=root)
    inside = Invocation(json_output=True)
    inside.command = "build"
    monkeypatch.setenv(container.INSIDE, "1")
    inside._module = held
    inside._hold_workspace()
    assert not (root / usage.FILE_NAME).exists()
    monkeypatch.delenv(container.INSIDE)
    here = Invocation(json_output=True)
    here.command = "build"
    here._module = held
    here._hold_workspace()
    assert len(usage.reasons(root)) == 1
    here.holds.close()
    assert usage.reasons(root) == []


def test_a_git_worktree_excludes_the_record(tmp_path):
    """git worktree の作業空間（.git がファイル）でも、実行中の記録は除外に入り、新しいファイルとして出ない。"""
    from helpers import git
    main = tmp_path / "main"
    git(tmp_path, "init", "--quiet", "--initial-branch=main", str(main))
    (main / "README.md").write_text("x\n", encoding="utf-8")
    git(main, "add", "README.md")
    git(main, "commit", "--quiet", "-m", "init")
    git(main, "worktree", "add", "--quiet", str(tmp_path / "other"))
    with usage.running(tmp_path / "other", "build"):
        assert git(tmp_path / "other", "status", "--porcelain", "--untracked-files=all").strip() == ""
