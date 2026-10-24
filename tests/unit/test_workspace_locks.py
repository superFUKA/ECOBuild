"""作業空間のロック（ecobuild.locks）：手動・コマンドの実行中・エージェント・コンテナ・--force。"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fake_docker import FakeDocker
import ecobuild_agent
import ecobuild_bundle  # noqa: F401（拡張の判断の口をつなぐ）
import ecobuild_container as container
from ecobuild import config, locks
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


def test_manual_lock_and_unlock(root):
    assert not locks.status(root).locked
    locks.lock(root, "調査中")
    state = locks.status(root)
    assert state.locked and [(r.kind, r.pid) for r in state.reasons] == [("manual", None)]
    assert "調査中" in state.reasons[0].text and state.reasons[0].since
    locks.unlock(root)
    assert not locks.status(root).locked and not (root / locks.FILE_NAME).exists()


def test_command_lock_is_held_only_while_running(root):
    with locks.running(root, "build"):
        reason = locks.status(root).reasons[0]
        assert (reason.kind, reason.pid) == ("command", os.getpid()) and "build" in reason.text
        with locks.running(root, "test"):
            assert len(locks.status(root).reasons) == 2
        assert len(locks.status(root).reasons) == 1
    assert not locks.status(root).locked


def test_command_lock_of_dead_process_is_released(root):
    data = {"commands": [{"id": "x", "pid": dead_pid(), "command": "build", "since": locks.now()}]}
    (root / locks.FILE_NAME).write_text(json.dumps(data), encoding="utf-8")
    assert not locks.status(root).locked


def test_agent_lock_follows_the_process(root):
    """作業空間のエージェントの誰か1人でも動いていればロック（エージェントごとの running.json）。"""
    from ecobuild_agent import agents
    first = agents.create(registration="worker", workspace=root)
    helper = agents.create(registration="worker", workspace=root, kind=agents.HELPER, parent=first.id)
    folder = status.prepare(first.folder, root)
    assert not locks.status(root).locked
    status.started(folder, os.getpid())
    reason = locks.status(root).reasons[0]
    assert (reason.kind, reason.pid) == ("agent", os.getpid()) and reason.since and first.id in reason.text
    status.started(folder, os.getpid(), status.APP)
    assert "係" in locks.status(root).reasons[0].text
    status.started(folder, dead_pid())
    assert not locks.status(root).locked
    status.started(helper.folder, os.getpid())                           # 手伝いだけが動いていても
    assert [r.kind for r in locks.status(root).reasons] == ["agent"]
    status.started(helper.folder, dead_pid())
    assert not locks.status(root).locked


def test_a_running_container_is_no_lock_and_docker_is_not_called(tmp_path, monkeypatch):
    """コンテナが動いていることはロックの理由にしない。ロックの確認は docker（Windows では WSL）を呼ばない：GUI が
    20 秒おきに読むたびに、止まっていた WSL を起こし続けていた。"""
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
    assert [s.locked for s in locks.status_of(roots)] == [False, False]
    assert fake.calls == []


def test_commands_inside_the_container_do_not_write_the_lock(root, monkeypatch):
    """コンテナの中の ecobuild は lock.json に書かない（中の pid はこのPCでは確かめられず、このPCの記録を消してしまう）。
    渡しているこのPCの CLI がロックする（_inside.route）。"""
    from types import SimpleNamespace
    from ecobuild_cli._output import Invocation

    held = SimpleNamespace(root=root)
    inside = Invocation(json_output=True)
    inside.command = "build"
    monkeypatch.setenv(container.INSIDE, "1")
    inside._module = held
    inside._hold_workspace()
    assert not (root / locks.FILE_NAME).exists()
    monkeypatch.delenv(container.INSIDE)
    here = Invocation(json_output=True)
    here.command = "build"
    here._module = held
    here._hold_workspace()
    assert [r.kind for r in locks.status(root).reasons] == ["command"]
    here.holds.close()
    assert not locks.status(root).locked


def test_force_ignores_automatic_locks_while_the_cause_continues(root):
    from ecobuild_agent import agents
    folder = status.prepare(agents.create(registration="worker", workspace=root).folder, root)
    status.started(folder, os.getpid())
    locks.lock(root, "手動")
    locks.unlock(root, force=True)                      # 手動も外れ、自動は無視される
    assert not locks.status(root).locked
    status.started(folder, os.getpid())                 # 同じ pid でも、起動し直した（別の原因）ならまた止まる
    assert locks.status(root).locked
    locks.unlock(root, force=True)
    assert not locks.status(root).locked
    with locks.running(root, "build"):                  # 新しい原因（実行中のコマンド）は無視されない
        assert locks.status(root).locked


def test_plain_unlock_does_not_release_automatic_locks(root):
    with locks.running(root, "check"):
        locks.lock(root)
        locks.unlock(root)
        assert [r.kind for r in locks.status(root).reasons] == ["command"]


def test_a_git_worktree_excludes_the_lock_files(tmp_path):
    """git worktree の作業空間（.git がファイル）でも、ロックのファイルは除外に入り、新しいファイルとして出ない。"""
    from helpers import git
    main = tmp_path / "main"
    git(tmp_path, "init", "--quiet", "--initial-branch=main", str(main))
    (main / "README.md").write_text("x\n", encoding="utf-8")
    git(main, "add", "README.md")
    git(main, "commit", "--quiet", "-m", "init")
    git(main, "worktree", "add", "--quiet", str(tmp_path / "other"))
    locks.lock(tmp_path / "other", "作業中")
    assert git(tmp_path / "other", "status", "--porcelain", "--untracked-files=all").strip() == ""
