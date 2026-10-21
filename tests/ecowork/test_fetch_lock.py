"""fetch を clone ごとに1つずつにする・読むだけのコマンドは取得できなくても答える・持ち主の違う場所のエラー。"""

import threading
import time

import pytest

from ecotask.process import Completed
from ecowork import git as _git
from ecowork.errors import ErrorCode
from ecowork.git import Git

pytestmark = pytest.mark.local


def _count_fetches(repo, monkeypatch, fetches):
    run = repo.run
    monkeypatch.setattr(repo, "run", lambda *args, **kw: (fetches.append(args) if args[0] == "fetch" else None)
                        or run(*args, **kw))


def _hold_lock(work):
    path = work / Git(work).output("rev-parse", "--git-path", _git.FETCH_LOCK)
    file = open(path, "a+")
    assert _git._lock_file(file, 1)
    return file


def test_fetch_waits_for_another_fetch_and_reuses_it(remote_and_clone, monkeypatch):
    """別のコマンドが fetch している間は待ち、その間に取得されたら（reuse なら）取得し直さない。"""
    _, work = remote_and_clone
    repo = Git(work)
    fetches = []
    _count_fetches(repo, monkeypatch, fetches)
    held = _hold_lock(work)
    done = threading.Event()
    thread = threading.Thread(target=lambda: (repo.fetch(reuse=True), done.set()))
    thread.start()
    time.sleep(0.3)
    assert not done.is_set()          # ロックを待っている
    Git(work)._mark().touch()         # 別のコマンドが取得し終えた
    _git._unlock_file(held)
    held.close()
    thread.join(10)
    assert done.is_set() and fetches == []


def test_fetch_goes_ahead_when_the_lock_is_not_released(remote_and_clone, monkeypatch):
    """ロックを待ちきれなければ、ロックなしで取得する（止まったままにしない）。"""
    _, work = remote_and_clone
    monkeypatch.setattr(_git, "FETCH_LOCK_TIMEOUT", 0.2)
    repo = Git(work)
    fetches = []
    _count_fetches(repo, monkeypatch, fetches)
    held = _hold_lock(work)
    try:
        repo.fetch()
    finally:
        _git._unlock_file(held)
        held.close()
    assert len(fetches) == 1


def test_dubious_ownership_is_its_own_error():
    """持ち主の違う場所（safe.directory）は git_error ではなく unsafe_repository と、信頼する場所に足す案内。"""
    completed = Completed(("git", "status"), 128, "",
                          "fatal: detected dubious ownership in repository at 'C:/work/m'\n"
                          "To add an exception for this directory, call: ...")
    error = _git._git_error(completed)
    assert error.code == ErrorCode.UNSAFE_REPOSITORY
    assert 'safe.directory "C:/work/m"' in error.hint and "dubious ownership" in error.details


def test_reading_commands_answer_from_the_local_copy_when_fetch_fails(repository):
    """task status・task list は、GitHubの最新を取得できなくても手元の写しで答え、そのことを知らせる。"""
    task = repository.create_task("読むだけ")
    repository.git.run("remote", "set-url", "origin", str(repository.root / "no-such-remote"))
    status = repository.task_status(task.number)
    assert status.number == task.number
    assert [t.number for t in repository.tasks()] == [task.number]
    assert any("手元の写しで表示しています" in n for n in repository.notices)
