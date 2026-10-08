"""ecotask：GitHubをデータベースとして使うタスク管理。偽のGitHubだけで確かめる（git は使わない）。"""

import datetime

import pytest

from fakes import FakeGitHub
from ecotask.board import BoardSettings, default_schema, default_stages
from ecotask.errors import ErrorCode, TaskError
from ecotask.tracker import Tracker, WorkState


def code_of(action):
    with pytest.raises(TaskError) as error:
        action()
    return error.value.code


@pytest.fixture
def tracker(tmp_path):
    return Tracker(tmp_path, github=FakeGitHub(tmp_path / "gh"), command="ecobuild")


def connect(tracker, **options):
    """標準のボードを作ってつなぐ。"""
    board = tracker.create_board("計画", **options)
    stages = default_stages(board.field("Status"))
    tracker.board = BoardSettings(board.url, "Status", stages, default_schema(board))
    return board


def status(tracker, number):
    return tracker.board_values(number).get("Status")


def test_standard_board(tracker):
    board = connect(tracker, sprint_start="2026-10-05")
    assert [o.name for o in board.field("Status").options] == ["Backlog", "Todo", "In Progress", "In Review", "Done"]
    assert [o.name for o in board.field("Priority").options] == ["High", "Middle", "Low"]
    assert (board.field("Estimate").type, board.field("Due").type) == ("NUMBER", "DATE")
    sprint = board.field("Sprint")
    assert [(o.name, o.start, o.duration) for o in sprint.options] == [
        ("Sprint 1", "2026-10-05", 14), ("Sprint 2", "2026-10-19", 14), ("Sprint 3", "2026-11-02", 14)]
    assert tracker.board.stages == {"todo": "Todo", "in_progress": "In Progress", "in_review": "In Review",
                                    "done": "Done"}
    assert code_of(lambda: tracker.create_board(" ")) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: tracker.create_board("x", sprint_start="10/5")) == ErrorCode.INVALID_ARGUMENT


def test_parent_follows_started_child(tracker):
    connect(tracker)
    parent = tracker.create("親")
    child = tracker.create("子", parent=parent.number)
    tracker.set_field(parent.number, "Status", "Backlog")
    tracker.set_stage(child.number, "in_progress")
    assert (status(tracker, child.number), status(tracker, parent.number)) == ("In Progress", "In Progress")
    tracker.close(child.number)
    assert status(tracker, parent.number) == "In Progress"            # 親を完了にするのは閉じたとき
    assert any(f"#{parent.number}" in n for n in tracker.notices)
    tracker.close(parent.number)
    assert status(tracker, parent.number) == "Done"


def test_sync_moves_parent_of_started_child(tracker):
    connect(tracker)
    parent = tracker.create("親")
    child = tracker.create("子", parent=parent.number)
    other = tracker.create("他")
    result = tracker.sync_board({child.number: WorkState(branch=True)})
    assert {(c.number, c.after) for c in result.changed} == {(child.number, "In Progress"),
                                                              (parent.number, "In Progress")}
    assert status(tracker, other.number) == "Todo"


def test_sprints(tracker):
    monday = datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())
    connect(tracker, sprint_start=(monday - datetime.timedelta(days=14)).isoformat())
    last, now, later = (tracker.create(t) for t in ("前", "今", "次"))
    tracker.set_field(last.number, "Sprint", "Sprint 1")
    tracker.set_field(now.number, "Sprint", "current")              # 今日を含むスプリント（Sprint 2）
    tracker.set_field(later.number, "Sprint", "Sprint 3")
    assert [t.number for t in tracker.tasks(sprint="current")] == [now.number]
    assert [t.number for t in tracker.tasks(sprint="sprint 3")] == [later.number]
    assert code_of(lambda: tracker.tasks(sprint="Sprint 9")) == ErrorCode.INVALID_ARGUMENT
    ordered = tracker.sort(tracker.tasks(), "Sprint")
    assert [t.number for t in ordered] == [last.number, now.number, later.number]


def test_without_board(tracker):
    """ボードがなくても、Issue・親子・依存・マイルストーンは使える（ボードの操作は no_board）。"""
    first = tracker.create("先")
    second = tracker.create("後", blocked_by=(first.number,))
    assert code_of(lambda: tracker.check_startable(second.number)) == ErrorCode.TASK_BLOCKED
    assert [t.number for t in tracker.tasks() if tracker.startable(t)] == [first.number]
    assert tracker.details(second.number).board is None
    assert code_of(lambda: tracker.set_field(first.number, "Priority", "High")) == ErrorCode.NO_BOARD
    assert code_of(lambda: tracker.tasks(sprint="current")) == ErrorCode.NO_BOARD


def test_tasks_are_typed(tracker):
    """保存の層：GitHubのデータ（Issue・ボードの値・マイルストーン）を、型の付いた Task にする。"""
    connect(tracker, sprint_start="2026-10-05")
    tracker.create_milestone("v1", due="2026-10-31")
    parent = tracker.create("親", milestone="v1")
    child = tracker.create("子", parent=parent.number)
    tracker.plan(child.number, priority="Middle", due="2026-10-20", estimate="2.5", sprint="Sprint 2")
    tracker.set_field(parent.number, "Status", "Backlog")
    task = tracker.task(child.number)
    assert (task.priority, task.priority_rank, task.due, task.estimate) == ("Middle", 1, datetime.date(2026, 10, 20), 2.5)
    assert (task.sprint.name, task.sprint.start, task.stage, task.parent) == (
        "Sprint 2", datetime.date(2026, 10, 19), "todo", parent.number)
    assert task.fields == {}                                   # 役割に当てた項目は fields に残さない
    planned = tracker.task(parent.number)
    assert (planned.stage, planned.status, planned.subtasks, planned.milestone_due) == (
        "planned", "Backlog", 1, datetime.date(2026, 10, 31))
    cleared = tracker.plan(child.number, clear=("due", "estimate"))
    assert (cleared.due, cleared.estimate, cleared.priority) == (None, None, "Middle")


def test_plan_is_checked(tracker):
    connect(tracker)
    task = tracker.create("t")
    assert code_of(lambda: tracker.plan(task.number)) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: tracker.plan(task.number, due="明日")) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: tracker.plan(task.number, priority="最高")) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: tracker.plan(task.number, due="2026-10-01", clear=("due",))) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: tracker.plan(task.number, clear=("size",))) == ErrorCode.INVALID_ARGUMENT
    tracker.board = BoardSettings(tracker.board.url, "Status", tracker.board.stages, {})   # 役割を当てていない
    assert code_of(lambda: tracker.plan(task.number, priority="High")) == ErrorCode.FIELD_NOT_FOUND
    assert code_of(lambda: tracker.deadlines()) == ErrorCode.FIELD_NOT_FOUND


def test_next_and_sprint_status_from_github(tracker):
    monday = datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())
    connect(tracker, sprint_start=monday.isoformat())
    low, high, overdue = (tracker.create(t) for t in ("低", "高", "遅れ"))
    tracker.plan(low.number, priority="Low", sprint="current", estimate="1")
    tracker.plan(high.number, priority="High", estimate="3")
    tracker.plan(overdue.number, due=(datetime.date.today() - datetime.timedelta(days=1)).isoformat())
    assert [n.task.number for n in tracker.next_tasks()] == [overdue.number, low.number, high.number]
    assert [n.task.number for n in tracker.next_tasks(exclude={overdue.number})][0] == low.number
    summary = tracker.sprint_status("current")
    assert (summary.sprint.name, summary.total, summary.estimate_remaining) == ("Sprint 1", 1, 1)
    assert [t.number for t in tracker.deadlines().overdue] == [overdue.number]


def test_next_tells_what_is_not_used(tracker):
    """計画の値の項目を当てていなければ、使わずに並べたことを知らせる（黙って順位が変わらないように）。"""
    tracker.create("t")
    tracker.next_tasks()
    assert any("ボードをつないでいない" in n for n in tracker.notices)
    connect(tracker)
    tracker.board = BoardSettings(tracker.board.url, "Status", tracker.board.stages, {"priority": "Priority"})
    tracker.notices.clear()
    tracker.next_tasks()
    assert any("期限・見積もり・スプリント" in n for n in tracker.notices)
