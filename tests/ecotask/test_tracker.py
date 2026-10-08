"""ecotask：GitHubをデータベースとして使うタスク管理。偽のGitHubだけで確かめる（git は使わない）。"""

import datetime

import pytest

from fakes import FakeGitHub
from ecotask.board import BoardSettings, default_stages
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
    tracker.board = BoardSettings(board.url, "Status", stages)
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
    tracker.set_field(now.number, "Sprint", "Sprint 2")
    tracker.set_field(later.number, "Sprint", "Sprint 3")
    assert [r.issue.number for r in tracker.rows(sprint="current")] == [now.number]
    assert [r.issue.number for r in tracker.rows(sprint="sprint 3")] == [later.number]
    assert code_of(lambda: tracker.rows(sprint="Sprint 9")) == ErrorCode.INVALID_ARGUMENT
    ordered = tracker.sort(tracker.rows(), "Sprint")
    assert [r.issue.number for r in ordered] == [last.number, now.number, later.number]


def test_without_board(tracker):
    """ボードがなくても、Issue・親子・依存・マイルストーンは使える（ボードの操作は no_board）。"""
    first = tracker.create("先")
    second = tracker.create("後", blocked_by=(first.number,))
    assert code_of(lambda: tracker.check_startable(second.number)) == ErrorCode.TASK_BLOCKED
    assert [r.issue.number for r in tracker.rows() if tracker.startable(r)] == [first.number]
    assert tracker.details(second.number).board is None
    assert code_of(lambda: tracker.set_field(first.number, "Priority", "High")) == ErrorCode.NO_BOARD
    assert code_of(lambda: tracker.rows(sprint="current")) == ErrorCode.NO_BOARD
