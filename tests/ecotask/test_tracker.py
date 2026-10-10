"""ecotask：GitHubをデータベースとして使うタスク管理。偽のGitHubだけで確かめる（git は使わない）。

計画・段階を置くボードは内部の保存場所：利用者はつながず、ECOBuildが見つけるか作る。
"""

import datetime

import pytest

from fakes import FakeGitHub
from ecotask.board import BoardField
from ecotask.errors import ErrorCode, TaskError
from ecotask.tracker import Tracker, WorkState

MONDAY = datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())


def code_of(action):
    with pytest.raises(TaskError) as error:
        action()
    return error.value.code


@pytest.fixture
def tracker(tmp_path):
    return Tracker(tmp_path, github=FakeGitHub(tmp_path / "gh"), command="ecobuild")


def status(tracker, number):
    """内部の状態の選択肢（ボードの Status）。"""
    return tracker.task(number).status


def test_board_is_made_when_first_needed(tracker):
    """読むだけなら作らない。タスクを作ると（段階を記録するため）決まった形のボードを作り、リンクして印を付ける。"""
    github = tracker.github
    assert tracker.tasks() == [] and github.boards == {}
    task = tracker.create("t")
    board = github.ecobuild_board()
    repository = github.repository_name(tracker.root)
    assert board.title == f"{repository.split('/')[-1]} タスク" and board.repositories == (repository,)
    assert [o.name for o in board.field("Status").options] == ["Backlog", "Todo", "In Progress", "In Review", "Done"]
    assert [o.name for o in board.field("Priority").options] == ["High", "Middle", "Low"]
    assert [board.field(n).type for n in ("Due", "Estimate", "Planned Start", "Planned End", "Started")] == [
        "DATE", "NUMBER", "DATE", "DATE", "DATE"]
    assert [(o.name, o.start, o.duration) for o in board.field("Sprint").options] == [
        (f"Sprint {i + 1}", (MONDAY + datetime.timedelta(days=14 * i)).isoformat(), 14) for i in range(3)]
    assert tracker.task(task.number).stage == "todo"
    tracker.create("u")
    assert len(github.boards) == 1                                   # 2つ目からは見つけて使う


def test_found_again_in_another_process(tracker, tmp_path):
    tracker.create("t")
    again = Tracker(tmp_path, github=tracker.github)
    assert again.task(1).stage == "todo" and len(tracker.github.boards) == 1


def test_other_boards_of_the_repository_are_not_used(tracker):
    """リポジトリにリンクした、印のないボード（人が作ったもの）は使わない。"""
    github = tracker.github
    other = github.add_board("人のボード")
    github.link_board(tracker.root, other.id, link=True)
    tracker.create("t")
    assert github.ecobuild_board().id != other.id and len(github.boards) == 2


def test_legacy_board_is_taken_over(tmp_path):
    """以前の設定（[board] の url）でつないでいたボードを引き継ぐ：印を付け、共同作業者に共有し、足りない項目を足す。"""
    github = FakeGitHub(tmp_path / "gh")
    github.collaborators = ("partner",)
    old = github.add_board("以前のボード", extra=(BoardField("F_due", "Due", "DATE"),))
    github.link_board(tmp_path, old.id, link=True)
    tracker = Tracker(tmp_path, github=github, legacy_board=old.url)
    task = tracker.create("t")
    tracker.plan(task.number, priority="High")
    assert github.ecobuild_board().id == old.id and len(github.boards) == 1
    assert github.shared_boards[old.id] == ("partner",)
    assert any("partner" in n for n in tracker.notices)
    assert tracker.task(task.number).priority == "High"


def test_board_is_shared_with_collaborators(tracker):
    tracker.github.collaborators = ("partner",)
    tracker.prepare()
    assert tracker.github.shared_boards[tracker.github.ecobuild_board().id] == ("partner",)
    assert any("partner" in n for n in tracker.notices)


def test_parent_follows_started_child(tracker):
    parent = tracker.create("親")
    child = tracker.create("子", parent=parent.number)
    tracker.set_stage(child.number, "in_progress")
    assert (status(tracker, child.number), status(tracker, parent.number)) == ("In Progress", "In Progress")
    tracker.close(child.number)
    assert status(tracker, parent.number) == "In Progress"            # 親を完了にするのは閉じたとき
    assert any(f"#{parent.number}" in n for n in tracker.notices)
    tracker.close(parent.number)
    assert status(tracker, parent.number) == "Done"


def test_sync_stages_fixes_drift(tracker):
    """GitHubのサイトでの操作などで段階がずれたら、作業の事実に合わせる（子が始まった親は作業中）。"""
    parent = tracker.create("親")
    child = tracker.create("子", parent=parent.number)
    other = tracker.create("他")
    closed = tracker.create("サイトで閉じた")
    tracker.github.close_issue(tracker.root, closed.number)              # ECOBuildを通さずに閉じた
    tasks = tracker.sync_stages(tracker.store.tasks(closed=True), {child.number: WorkState(branch=True)})
    assert {t.number: t.stage for t in tasks} == {parent.number: "in_progress", child.number: "in_progress",
                                                  other.number: "todo", closed.number: "done"}
    assert (status(tracker, parent.number), status(tracker, closed.number)) == ("In Progress", "Done")


def test_sync_stages_does_nothing_without_a_board(tracker):
    tracker.github.create_issue(tracker.root, "サイトで作った", "")
    tasks = tracker.store.tasks()
    assert tracker.sync_stages(tasks, {}) == tasks and tracker.github.boards == {}


def test_sprints(tracker):
    last, now, later = (tracker.create(t) for t in ("前", "今", "次"))
    tracker.plan(last.number, sprint="Sprint 3")
    tracker.plan(now.number, sprint="current")                         # 今日を含むスプリント（Sprint 1）
    tracker.plan(later.number, sprint="Sprint 2")
    assert [t.number for t in tracker.tasks(sprint="current")] == [now.number]
    assert [t.number for t in tracker.tasks(sprint="sprint 3")] == [last.number]
    assert code_of(lambda: tracker.tasks(sprint="Sprint 9")) == ErrorCode.INVALID_ARGUMENT
    ordered = tracker.sort(tracker.tasks(), "sprint")
    assert [t.number for t in ordered] == [now.number, later.number, last.number]


def test_sprints_are_extended_before_they_run_out(tracker):
    """スプリントが尽きそうなら、書くときに同じ日数で続きを足す（今あるスプリントとタスクの割り当ては残す）。"""
    task = tracker.create("t")
    tracker.plan(task.number, sprint="Sprint 1")
    store = tracker.store
    store._extend_sprints(today=MONDAY)                               # まだ6週間ある：足さない
    assert [s.name for s in tracker.sprints()] == ["Sprint 1", "Sprint 2", "Sprint 3"]
    store._extend_sprints(today=MONDAY + datetime.timedelta(days=35))   # 最後の Sprint 3 の途中
    sprints = tracker.sprints()
    assert [s.name for s in sprints] == ["Sprint 1", "Sprint 2", "Sprint 3", "Sprint 4", "Sprint 5"]
    assert sprints[3].start == MONDAY + datetime.timedelta(days=42) and sprints[3].days == 14
    assert tracker.task(task.number).sprint.name == "Sprint 1"


def test_without_board_yet(tracker):
    """まだ何も記録していなければ、計画の値なしで読める（スプリントは「まだありません」）。"""
    tracker.github.create_issue(tracker.root, "サイトで作った", "")
    assert [t.stage for t in tracker.tasks()] == [None]
    assert tracker.sprints() == [] and not tracker.deadlines().overdue
    assert code_of(lambda: tracker.tasks(sprint="current")) == ErrorCode.INVALID_ARGUMENT
    assert tracker.github.boards == {}


def test_tasks_are_typed(tracker):
    """保存の層：GitHubのデータ（Issue・ボードの値・マイルストーン）を、型の付いた Task にする。"""
    tracker.create_milestone("v1", due="2026-10-31")
    parent = tracker.create("親", milestone="v1")
    child = tracker.create("子", parent=parent.number)
    tracker.plan(child.number, priority="Middle", due="2026-10-20", estimate="2.5", sprint="Sprint 2")
    task = tracker.task(child.number)
    assert (task.priority, task.priority_rank, task.due, task.estimate) == ("Middle", 1, datetime.date(2026, 10, 20), 2.5)
    assert (task.sprint.name, task.sprint.start, task.stage, task.parent) == (
        "Sprint 2", MONDAY + datetime.timedelta(days=14), "todo", parent.number)
    item = tracker.store.item(parent.number)                           # GitHubのサイトで計画中にした
    tracker.store.write(item, tracker.store.info().field("Status"), "Backlog")
    planned = tracker.task(parent.number)
    assert (planned.stage, planned.subtasks, planned.milestone_due) == ("planned", 1, datetime.date(2026, 10, 31))
    cleared = tracker.plan(child.number, clear=("due", "estimate"))
    assert (cleared.due, cleared.estimate, cleared.priority) == (None, None, "Middle")


def test_plan_is_checked(tracker):
    task = tracker.create("t")
    assert code_of(lambda: tracker.plan(task.number)) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: tracker.plan(task.number, due="明日")) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: tracker.plan(task.number, priority="最高")) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: tracker.plan(task.number, due="2026-10-01", clear=("due",))) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: tracker.plan(task.number, clear=("size",))) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: tracker.sort([], "Priority")) == ErrorCode.INVALID_ARGUMENT   # 並べるのは値の名前


def test_missing_fields_are_added_back(tracker):
    """GitHubのサイトで項目を消されても、書くときに決まった項目を足し直す。"""
    tracker.create("t")
    github = tracker.github
    board = github.ecobuild_board()
    github.boards[board.number] = board.__class__(**{**board.__dict__, "fields": tuple(
        f for f in board.fields if f.name != "Estimate")})
    again = Tracker(tracker.root, github=github)
    assert again.plan(1, estimate="3").estimate == 3


def test_next_and_sprint_status_from_github(tracker):
    low, high, overdue = (tracker.create(t) for t in ("低", "高", "遅れ"))
    tracker.plan(low.number, priority="Low", sprint="current", estimate="1")
    tracker.plan(high.number, priority="High", estimate="3")
    tracker.plan(overdue.number, due=(datetime.date.today() - datetime.timedelta(days=1)).isoformat())
    assert [n.task.number for n in tracker.next_tasks()] == [overdue.number, low.number, high.number]
    assert [n.task.number for n in tracker.next_tasks(exclude={overdue.number})][0] == low.number
    summary = tracker.sprint_status("current")
    assert (summary.sprint.name, summary.total, summary.estimate_remaining) == ("Sprint 1", 1, 1)
    assert [t.number for t in tracker.deadlines().overdue] == [overdue.number]


def test_plan_returns_written_values_even_if_reading_is_stale(tracker, monkeypatch):
    """GitHubは書いた直後の読み取りで古い値を返すことがある。plan は書いた値を重ねて返す。"""
    task = tracker.create("t")
    tracker.plan(task.number, priority="Low", estimate="1")
    stale = tracker.task(task.number)
    monkeypatch.setattr(tracker.store, "task", lambda number: stale)     # 読み取りが古いまま
    result = tracker.plan(task.number, priority="High", due="2026-10-15", clear=("estimate",), sprint="sprint 2")
    assert (result.priority, result.priority_rank, result.due, result.estimate, result.sprint.name) == (
        "High", 0, datetime.date(2026, 10, 15), None, "Sprint 2")


def test_dates_are_recorded(tracker):
    """追加した日・終了日はGitHubの記録（Issueの作成・閉じた日時）、開始日は作業中になったとき記録する。"""
    today = datetime.date.today()
    parent = tracker.create("親")
    child = tracker.create("子", parent=parent.number)
    task = tracker.task(child.number)
    assert (task.created, task.started, task.finished) == (today, None, None)
    tracker.set_stage(child.number, "in_progress")
    assert (tracker.task(child.number).started, tracker.task(parent.number).started) == (today, today)
    tracker.store.write(tracker.store.item(child.number), tracker.store.info().field("Started"), "2026-01-02")
    tracker.set_stage(child.number, "in_review")                       # 開始日は最初の1回だけ
    assert tracker.task(child.number).started == datetime.date(2026, 1, 2)
    tracker.close(child.number)
    assert tracker.task(child.number).finished == today
    tracker.reopen(child.number)
    assert (tracker.task(child.number).finished, tracker.task(child.number).started) == (None, datetime.date(2026, 1, 2))


def test_create_and_edit_with_planned_dates(tracker):
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
    before = len(tracker.github.issues)
    assert code_of(lambda: tracker.create("t", plan={"planned_start": "2026-10-20", "planned_end": "2026-10-12"})) \
        == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: tracker.create("t", plan={"due": "10/31"})) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: tracker.create("t", plan={"due": "2026-02-30"})) == ErrorCode.INVALID_ARGUMENT
    assert len(tracker.github.issues) == before                            # Issueは作っていない


def test_planning_stage(tracker):
    """作業を始める前の段階（計画中・未着手）は task plan で変える。作業を始めたものは変えない。"""
    task = tracker.create("t")
    assert tracker.plan(task.number, stage="planned").stage == "planned"
    assert (tracker.task(task.number).stage, status(tracker, task.number)) == ("planned", "Backlog")
    assert tracker.plan(task.number, stage="todo", priority="High").priority == "High"
    assert tracker.task(task.number).stage == "todo"
    assert code_of(lambda: tracker.plan(task.number, stage="done")) == ErrorCode.INVALID_ARGUMENT
    tracker.set_stage(task.number, "in_progress")
    assert code_of(lambda: tracker.plan(task.number, stage="planned")) == ErrorCode.INVALID_ARGUMENT
    tracker.close(task.number)
    assert code_of(lambda: tracker.plan(task.number, stage="todo")) == ErrorCode.TASK_CLOSED
