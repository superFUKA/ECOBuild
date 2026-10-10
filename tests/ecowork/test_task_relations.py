"""タスクの親子・依存・マイルストーンと、作業の流れとの連動。偽のGitHub＋手元のbareで確かめる。"""

import pytest

from helpers import write
from ecowork.errors import ErrorCode, WorkError

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def finish(repository, number, name):
    workspace = repository.task(number).start()
    write(repository.root / name, "x\n")
    workspace.stage(name)
    workspace.commit(name)
    workspace.submit()
    result = repository.pull_request().merge()
    repository.clean_workspaces()
    return result


def test_relations_are_shown_and_ready_tasks_are_listed(repository):
    repository.create_milestone("v1", due="2026-10-31")
    parent = repository.create_task("親")
    first = repository.create_task("先", parent=parent.number)
    second = repository.create_task("後", parent=parent.number, blocked_by=(first.number,), milestone="v1")
    listed = {t.number: t for t in repository.tasks()}
    assert (listed[parent.number].subtasks, listed[parent.number].subtasks_done) == (2, 0)
    assert (listed[second.number].parent, listed[second.number].blocked_by,
            listed[second.number].milestone) == (parent.number, 1, "v1")
    assert [t.number for t in repository.tasks(ready=True)] == [first.number]
    assert [t.number for t in repository.tasks(milestone="v1")] == [second.number]

    status = repository.task_status(second.number)
    assert status.parent.number == parent.number and [b.number for b in status.blocked_by] == [first.number]
    assert [s.number for s in repository.task_status(parent.number).subtasks] == [first.number, second.number]
    assert [b.number for b in repository.task_status(first.number).blocking] == [second.number]


def test_subtasks_branch_from_the_parent_workspace(repository):
    """子タスクの作業空間は親の作業空間から派生し、PRは親の作業空間へ。子が終わらないと親は終了できない。"""
    parent = repository.create_task("親")
    first = repository.create_task("先", parent=parent.number)
    second = repository.create_task("後", parent=parent.number, blocked_by=(first.number,))
    parent_branch = f"task/{parent.number}"
    assert code_of(lambda: repository.task(second.number).start()) == ErrorCode.TASK_BLOCKED
    assert code_of(lambda: repository.close_task(parent.number)) == ErrorCode.OPEN_SUBTASKS
    assert code_of(lambda: repository.task(first.number).start(base="main")) == ErrorCode.INVALID_BASE

    workspace = repository.task(first.number).start()           # 親の作業空間は、なければGitHubに作る
    assert workspace.base == parent_branch and repository.git.has_remote_branch(parent_branch)
    assert any(parent_branch in n for n in repository.notices)
    write(repository.root / "a.txt", "x\n")
    workspace.stage("a.txt")
    workspace.commit("a")
    pr = workspace.submit()
    assert pr.base == parent_branch
    assert repository.pull_request().merge().closed_issue == first.number    # 親の作業空間へ入れて子を閉じる
    repository.clean_workspaces()
    assert not any("すべて閉じました" in n for n in repository.notices)   # 子がまだ残っている

    workspace = repository.task(second.number).start()
    assert workspace.base == parent_branch and (repository.root / "a.txt").exists()   # 親の最新から
    write(repository.root / "b.txt", "y\n")
    workspace.stage("b.txt")
    workspace.commit("b")
    workspace.submit()

    parent_workspace = repository.task(parent.number).start()   # 親も作業できる（作成元は main）
    assert parent_workspace.base == "main" and (repository.root / "a.txt").exists()
    write(repository.root / "p.txt", "p\n")
    parent_workspace.stage("p.txt")
    parent_workspace.commit("p")
    repository.notices.clear()
    parent_pr = parent_workspace.submit()
    assert any("子タスクが終わるまでマージできません" in n for n in repository.notices)
    assert code_of(lambda: parent_pr.merge()) == ErrorCode.OPEN_SUBTASKS
    assert code_of(lambda: repository.drop_workspace(parent.number, close=True, discard=True)) == ErrorCode.OPEN_SUBTASKS

    repository.task(second.number).start()
    repository.pull_request().merge()
    assert any(f"#{parent.number}" in n and "すべて閉じました" in n for n in repository.notices)
    repository.task(parent.number).start()
    repository.sync()                                            # 子の変更を親の手元へ
    assert (repository.root / "b.txt").exists()
    result = repository.pull_request().merge()
    assert result.closed_issue == parent.number
    repository.clean_workspaces()
    repository.sync()
    assert all((repository.root / name).exists() for name in ("a.txt", "b.txt", "p.txt"))


def test_parent_without_code_is_closed_after_subtasks(repository):
    """コードを変えない親（作業空間なし）は、子が終わってから task close で閉じる。"""
    parent = repository.create_task("親")
    child = repository.create_task("子", parent=parent.number)
    assert code_of(lambda: repository.close_task(parent.number)) == ErrorCode.OPEN_SUBTASKS
    repository.close_task(child.number)
    assert repository.close_task(parent.number).state == "closed"


def test_blocked_task_can_be_started_explicitly(repository):
    first = repository.create_task("先")
    second = repository.create_task("後", blocked_by=(first.number,))
    workspace = repository.task(second.number).start(ignore_blocked=True)
    assert workspace.number == second.number
    # 一度始めた作業空間へ戻るときは止めない
    repository.task(first.number).start()
    assert repository.task(second.number).start().number == second.number


def test_editing_relations(repository):
    one, two, three = (repository.create_task(t) for t in ("一", "二", "三"))
    repository.edit_task(three.number, parent=one.number, add_blocked_by=(two.number,))
    assert code_of(lambda: repository.edit_task(three.number, parent=two.number)) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: repository.edit_task(three.number, parent=three.number)) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: repository.edit_task(three.number, milestone="ない")) == ErrorCode.MILESTONE_NOT_FOUND
    repository.edit_task(three.number, clear_parent=True, remove_blocked_by=(two.number,))
    status = repository.task_status(three.number)
    assert (status.parent, status.blocked_by) == (None, ())


def test_milestones(repository):
    repository.create_milestone("v1", due="2026-10-31", description="最初")
    assert code_of(lambda: repository.create_milestone("v1")) == ErrorCode.ALREADY_EXISTS
    task = repository.create_task("t", milestone="v1")
    assert task.milestone == "v1"
    renamed = repository.edit_milestone("v1", new_title="v1.0", due="")
    assert (renamed.title, renamed.due) == ("v1.0", None)
    assert repository.task(task.number).milestone == "v1.0"
    assert repository.edit_milestone("v1.0", state="closed").state == "closed"
    assert repository.milestones() == [] and len(repository.milestones(closed=True)) == 1
    assert repository.edit_task(task.number, clear_milestone=True).milestone is None
