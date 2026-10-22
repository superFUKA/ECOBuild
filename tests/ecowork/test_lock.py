"""使用中（ロック中）の作業空間を守る：ブランチの切り替えと、ロック中のほかの作業空間が使っているタスクブランチの削除を止める。

ロックの判断は利用側（Hooks.switch_locks・branch_locks）が持つ。ここでは差し込みの効き方を確かめる。
"""

import pytest

from helpers import git, write
from ecowork import Hooks, Repository
from ecowork.errors import ErrorCode, WorkError

pytestmark = pytest.mark.local


class Locked(Hooks):
    def __init__(self, switch=(), branch=()):
        self.switch, self.branch, self.asked = list(switch), list(branch), []

    def switch_locks(self, repository):
        return list(self.switch)

    def branch_locks(self, repository, branch):
        self.asked.append(branch)
        return list(self.branch)


def refused(action):
    with pytest.raises(WorkError) as error:
        action()
    assert error.value.code == ErrorCode.WORKSPACE_LOCKED
    return error.value


def test_start_another_task_is_refused_while_locked(repository):
    first = repository.create_task("a").start()
    second = repository.create_task("b")
    repository.hooks = Locked(switch=["エージェントが動いています"])
    error = refused(second.start)
    assert error.details == ["エージェントが動いています"] and "workspace unlock" in error.hint
    assert "--force" not in error.hint
    assert repository.git.current_branch() == first.branch   # 何も変わっていない
    assert not repository.git.has_local_branch("task/2")


def test_start_the_current_task_is_not_a_switch(repository):
    task = repository.create_task("a")
    task.start()
    repository.hooks = Locked(switch=["使用中"])
    assert task.start().branch == "task/1"


def test_drop_current_refused_and_other_branch_allowed(repository):
    first = repository.create_task("a").start()
    write(repository.root / "a.txt", "a\n")
    first.record("a")
    first.push()
    repository.git.switch("main")
    second = repository.create_task("b").start()
    repository.hooks = Locked(switch=["使用中"])
    refused(lambda: repository.drop_task(2, discard=True))      # 今いるタスクブランチを消す＝切り替わる
    assert repository.git.has_local_branch("task/2")
    refused(lambda: repository.remove_task_branch(2))
    assert repository.drop_task(1, discard=True).branch == "task/1"   # 今いないものは、切り替えにならない


def test_other_workspace_lock_stops_deleting_its_branch(repository):
    task = repository.create_task("a").start()
    repository.git.switch("main")
    hooks = repository.hooks = Locked(branch=["/work/other：エージェントが動いています"])
    error = refused(lambda: repository.drop_task(1, discard=True))
    assert error.details == ["/work/other：エージェントが動いています"]
    refused(lambda: repository.remove_task_branch(1))
    assert repository.git.has_local_branch("task/1") and repository.git.has_remote_branch("task/1")
    assert "task/1" in hooks.asked and task.number == 1
    hooks.branch = []
    assert repository.drop_task(1, discard=True).branch == "task/1"


def test_prune_skips_locked_and_refuses_when_named(repository):
    repository.create_task("a").start()
    repository.git.switch("main")
    repository.github.close_issue(repository.root, 1)
    repository.hooks = Locked(branch=["/work/other：使用中"])
    skipped = repository.prune_task_branches().skipped
    assert [s.branch for s in skipped] == ["task/1"] and "ロック中" in skipped[0].reason
    refused(lambda: repository.prune_task_branch(1))
    assert repository.git.has_local_branch("task/1")
    repository.hooks = Locked()
    assert repository.prune_task_branches().removed == ("task/1",)


def test_prune_current_is_refused_while_locked(repository):
    repository.create_task("a").start()
    repository.github.close_issue(repository.root, 1)
    repository.hooks = Locked(switch=["使用中"])
    assert [s.branch for s in repository.prune_task_branches().skipped] == ["task/1"]
    assert repository.git.current_branch() == "task/1"


@pytest.mark.needs_git_2_48
def test_review_does_not_touch_a_locked_workspace_and_a_locked_review_workspace_is_kept(repository, tmp_path):
    task = repository.create_task("a").start()
    write(repository.root / "a.txt", "a\n")
    task.record("a")
    task.submit()
    repository.hooks = Locked(switch=["使用中"])
    review = repository.review_task(1, tmp_path / "r")      # 確認は別の作業空間：この作業空間は変わらない
    assert repository.git.current_branch() == "task/1"
    inside = Repository(review.workspace, github=repository.github, hooks=Locked(switch=["使用中"]))
    refused(inside.end_review)
    assert (tmp_path / "r").exists()
    assert Repository(review.workspace, github=repository.github).end_review().workspace is not None


@pytest.mark.needs_git_2_48
def test_a_locked_workspace_keeps_its_finished_branch(repository, tmp_path):
    started = repository.start_task_in(repository.create_task("a").number, tmp_path / "1")
    inside = Repository(started.workspace, github=repository.github, hooks=Locked(switch=["使用中"]))
    repository.github.close_issue(repository.root, 1)
    assert [s.branch for s in inside.prune_task_branches().skipped] == ["task/1"]
    assert (tmp_path / "1").exists() and repository.git.has_local_branch("task/1")


def test_tidy_leaves_finished_branch_used_elsewhere(repository):
    repository.create_task("a").start()
    repository.git.switch("main")
    git(repository.root, "push", "origin", "--delete", "task/1")
    repository.github.close_issue(repository.root, 1)
    repository.hooks = Locked(branch=["/work/other：使用中"])
    repository.git.fetch()
    assert repository._tidy_finished() == ()
    assert repository.git.has_local_branch("task/1") and any("残しました" in n for n in repository.notices)
    repository.hooks = Locked()
    assert repository._tidy_finished() == ("task/1",)


def test_tidy_leaves_finished_branch_checked_out_in_another_git_worktree(repository, tmp_path):
    # git worktree が取り出しているブランチは git が消させない：片付けで止まらずに残す
    repository.create_task("a").start()
    repository.git.switch("main")
    git(repository.root, "push", "origin", "--delete", "task/1")
    repository.github.close_issue(repository.root, 1)
    git(repository.root, "worktree", "add", str(tmp_path / "other"), "task/1")
    repository.git.fetch()
    assert repository._tidy_finished() == ()
    assert repository.git.has_local_branch("task/1") and any("残しました" in n for n in repository.notices)
    git(repository.root, "worktree", "remove", str(tmp_path / "other"))
    assert repository._tidy_finished() == ("task/1",)
