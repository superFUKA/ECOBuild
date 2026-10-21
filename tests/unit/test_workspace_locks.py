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
    folder = status.prepare(container.name(root), root)
    assert not locks.status(root).locked
    status.started(folder, os.getpid())
    reason = locks.status(root).reasons[0]
    assert (reason.kind, reason.pid) == ("agent", os.getpid()) and reason.since
    status.started(folder, os.getpid(), status.APP)
    assert "係" in locks.status(root).reasons[0].text
    status.started(folder, dead_pid())
    assert not locks.status(root).locked


def test_container_lock_while_running(root, monkeypatch):
    fake = FakeDocker(monkeypatch)
    monkeypatch.setattr(docker, "run", fake.run)
    assert not locks.status(root).locked and not fake.calls   # コンテナにしていなければ docker を呼ばない
    container.choose(root, True, fake.run)
    assert not locks.status(root).locked                      # まだコンテナがない
    fake.containers[container.name(root)] = ["running", "image", "1"]
    reason = locks.status(root).reasons[0]
    assert reason.kind == "container" and container.name(root) in reason.text
    fake.containers[container.name(root)][0] = "exited"
    assert not locks.status(root).locked


def test_container_locks_are_checked_with_one_docker_call(tmp_path, monkeypatch):
    fake = FakeDocker(monkeypatch)
    monkeypatch.setattr(docker, "run", fake.run)
    roots = []
    for index in range(3):
        folder = tmp_path / f"w{index}"
        (folder / config.DIRECTORY).mkdir(parents=True)
        container.choose(folder, True, fake.run)
        roots.append(folder)
    fake.containers[container.name(roots[1])] = ["running", "image", "1"]
    fake.calls.clear()
    result = locks.status_of(roots)
    assert [s.locked for s in result] == [False, True, False]
    assert sum(1 for call in fake.calls if call[1] == "ps") == 1


def test_force_ignores_automatic_locks_while_the_cause_continues(root):
    folder = status.prepare(container.name(root), root)
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
