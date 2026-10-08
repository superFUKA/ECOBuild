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


def test_parent_and_blocked_tasks_are_not_started(repository):
    parent = repository.create_task("親")
    first = repository.create_task("先", parent=parent.number)
    second = repository.create_task("後", parent=parent.number, blocked_by=(first.number,))
    assert code_of(lambda: parent.start()) == ErrorCode.OPEN_SUBTASKS
    assert code_of(lambda: repository.task(second.number).start()) == ErrorCode.TASK_BLOCKED
    assert code_of(lambda: repository.close_task(parent.number)) == ErrorCode.OPEN_SUBTASKS

    finish(repository, first.number, "a.txt")
    assert repository.notices == []                          # 子がまだ残っている
    assert [t.number for t in repository.tasks(ready=True)] == [second.number]
    result = finish(repository, second.number, "b.txt")
    assert result.closed_issue == second.number
    assert any(f"#{parent.number}" in n for n in repository.notices)   # 子がすべて閉じたら知らせる
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
