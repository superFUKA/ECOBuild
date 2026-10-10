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


def test_board_is_dedicated_to_the_repository(tracker):
    """ボードはこのリポジトリ専用：作ったらリンクし、他のリポジトリと共有されたボードは、つなぐときに止める。"""
    board = tracker.create_board()
    repository = tracker.github.repository_name(tracker.root)
    assert board.title == f"{repository.split('/')[-1]} タスク" and board.repositories == (repository,)
    settings = BoardSettings(board.url, "Status", default_stages(board.field("Status")), default_schema(board))
    assert tracker.check_board(settings, exclusive=True).scope.problems == ()

    tracker.github.foreign_items[board.id] = {"tester/other": 2}
    assert code_of(lambda: tracker.check_board(settings, exclusive=True)) == ErrorCode.BOARD_SHARED
    shared = BoardSettings(board.url, "Status", settings.stages, settings.schema, shared=True)
    assert tracker.check_board(shared, exclusive=True).scope.foreign_items == 2      # 共有を許せば止めない

    tracker.board = settings
    tracker.github.boards[board.number] = tracker.github.boards[board.number].__class__(
        **{**tracker.github.boards[board.number].__dict__, "public": True})
    tracker.create_board("もう1つ")                               # 同じリポジトリに別のボード
    tracker.board_status()
    assert any("他のボードもリンク" in n for n in tracker.notices)
    assert any("他のリポジトリの項目" in n for n in tracker.notices)
    assert any("公開されています" in n for n in tracker.notices)


def test_plan_returns_written_values_even_if_reading_is_stale(tracker, monkeypatch):
    """GitHubは書いた直後の読み取りで古い値を返すことがある。plan は書いた値を重ねて返す。"""
    connect(tracker, sprint_start="2026-10-05")
    task = tracker.create("t")
    tracker.plan(task.number, priority="Low", estimate="1")
    stale = tracker.task(task.number)
    monkeypatch.setattr(tracker.store, "task", lambda number: stale)     # 読み取りが古いまま
    result = tracker.plan(task.number, priority="High", due="2026-10-15", clear=("estimate",), sprint="sprint 2")
    assert (result.priority, result.priority_rank, result.due, result.estimate, result.sprint.name) == (
        "High", 0, datetime.date(2026, 10, 15), None, "Sprint 2")


def test_standard_board_has_date_fields(tracker):
    board = connect(tracker)
    assert [(board.field(n).type) for n in ("Planned Start", "Planned End", "Started")] == ["DATE"] * 3
    assert {r: tracker.board.schema[r] for r in ("planned_start", "planned_end", "started")} == {
        "planned_start": "Planned Start", "planned_end": "Planned End", "started": "Started"}


def test_dates_are_recorded(tracker):
    """追加した日・終了日はGitHubの記録（Issueの作成・閉じた日時）、開始日は作業中になったときボードに書く。"""
    connect(tracker)
    today = datetime.date.today()
    parent = tracker.create("親")
    child = tracker.create("子", parent=parent.number)
    task = tracker.task(child.number)
    assert (task.created, task.started, task.finished) == (today, None, None)
    tracker.set_stage(child.number, "in_progress")
    assert (tracker.task(child.number).started, tracker.task(parent.number).started) == (today, today)
    tracker.set_field(child.number, "Started", "2026-01-02")
    tracker.set_stage(child.number, "in_review")                       # 開始日は最初の1回だけ
    assert tracker.task(child.number).started == datetime.date(2026, 1, 2)
    tracker.close(child.number)
    assert tracker.task(child.number).finished == today
    tracker.reopen(child.number)
    assert (tracker.task(child.number).finished, tracker.task(child.number).started) == (None, datetime.date(2026, 1, 2))


def test_started_is_skipped_without_the_field(tracker):
    connect(tracker)
    tracker.board = BoardSettings(tracker.board.url, "Status", tracker.board.stages, {"due": "Due"})
    task = tracker.create("t")
    tracker.set_stage(task.number, "in_progress")
    assert tracker.task(task.number).started is None and tracker.notices == []


def test_create_and_edit_with_planned_dates(tracker):
    connect(tracker)
    task = tracker.create("t", plan={"due": "2026-10-31", "planned_start": "2026-10-12", "planned_end": "2026-10-20"})
    got = tracker.task(task.number)
    assert (got.due, got.planned_start, got.planned_end) == (
        datetime.date(2026, 10, 31), datetime.date(2026, 10, 12), datetime.date(2026, 10, 20))
    tracker.edit(task.number, plan={"planned_end": "2026-10-25"}, clear_plan=("due",))
    got = tracker.task(task.number)
    assert (got.due, got.planned_start, got.planned_end) == (None, datetime.date(2026, 10, 12), datetime.date(2026, 10, 25))
    # 書かない方の今の値と合わせて、開始予定日が終了予定日より後なら止める
    assert code_of(lambda: tracker.edit(task.number, plan={"planned_start": "2026-10-30"})) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: tracker.plan(task.number, planned_end="2026-10-01")) == ErrorCode.INVALID_ARGUMENT
    assert tracker.plan(task.number, planned_start="2026-10-30", clear=("planned_end",)).planned_start == \
        datetime.date(2026, 10, 30)
    assert code_of(lambda: tracker.plan(task.number, clear=("started",))) == ErrorCode.INVALID_ARGUMENT
    ordered = tracker.sort(tracker.tasks(), "planned_start")
    assert [t.number for t in ordered] == [task.number]


def test_create_checks_dates_before_creating(tracker):
    connect(tracker)
    before = len(tracker.github.issues)
    assert code_of(lambda: tracker.create("t", plan={"planned_start": "2026-10-20", "planned_end": "2026-10-12"})) \
        == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: tracker.create("t", plan={"due": "10/31"})) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: tracker.create("t", plan={"due": "2026-02-30"})) == ErrorCode.INVALID_ARGUMENT
    assert len(tracker.github.issues) == before                            # Issueは作っていない
    tracker.board = None
    assert code_of(lambda: tracker.create("t", plan={"due": "2026-10-31"})) == ErrorCode.NO_BOARD


def test_add_standard_fields_to_an_existing_board(tracker):
    from ecotask.board import BoardField
    board = tracker.github.add_board(extra=(BoardField("F_due", "期日", "DATE"),))
    settings = BoardSettings(board.url, "Status", default_stages(board.field("Status")))
    added = tracker.add_standard_fields(BoardSettings(board.url, "Status", schema={"due": "期日"}))
    assert added == ("Priority", "Estimate", "Sprint", "Planned Start", "Planned End", "Started")
    schema = {**default_schema(tracker.github.get_board(tracker.root, "tester", board.number)), "due": "期日"}
    assert set(schema) == {"priority", "due", "estimate", "sprint", "planned_start", "planned_end", "started"}
    assert tracker.add_standard_fields(BoardSettings(settings.url, "Status", schema=schema)) == ()
