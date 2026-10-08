"""ボード（GitHub Projects）と作業の段階の連動。偽のGitHub＋手元のbareで確かめる。"""

import pytest

from helpers import write
from ecowork import Repository
from ecowork.board import BoardField, BoardOption, BoardSettings
from ecowork.errors import ErrorCode, WorkError

pytestmark = pytest.mark.local

STAGES = {"todo": "Todo", "in_progress": "In Progress", "in_review": "In Review", "done": "Done"}


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


@pytest.fixture
def boarded(repository):
    priority = BoardField("F_pri", "Priority", "SINGLE_SELECT", (BoardOption("P1", "High"), BoardOption("P2", "Low")))
    extra = (priority, BoardField("F_due", "Due", "DATE"), BoardField("F_est", "Estimate", "NUMBER"))
    board = repository.github.add_board(statuses=("Backlog", "Todo", "In Progress", "In Review", "Done"), extra=extra)
    return Repository(repository.root, github=repository.github, command="ecobuild",
                      board=BoardSettings(board.url, "Status", dict(STAGES)))


def status_of(repo, number):
    return repo.task_status(number).board.get("Status")


def commit(repo, workspace, name):
    write(repo.root / name, "x\n")
    workspace.stage(name)
    workspace.commit(name)


def test_stages_follow_the_work(boarded):
    task = boarded.create_task("t")
    assert status_of(boarded, task.number) == "Todo"
    workspace = task.start()
    assert status_of(boarded, task.number) == "In Progress"
    commit(boarded, workspace, "a.txt")
    pr = workspace.submit(draft=True)
    assert status_of(boarded, task.number) == "In Progress"      # 下書きは作業中のまま
    boarded.set_pull_request_draft(pr.number, draft=False)
    assert status_of(boarded, task.number) == "In Review"
    boarded.close_pull_request(pr.number)
    assert status_of(boarded, task.number) == "In Progress"
    boarded.reopen_pull_request(pr.number)
    assert status_of(boarded, task.number) == "In Review"
    boarded.pull_request(pr.number).merge()
    assert status_of(boarded, task.number) == "Done"
    assert boarded.notices == []

    other = boarded.create_task("やめる")
    other.start()
    boarded.drop_workspace(other.number)
    assert status_of(boarded, other.number) == "Todo"
    boarded.close_task(other.number)
    assert status_of(boarded, other.number) == "Done"
    boarded.reopen_task(other.number)
    assert status_of(boarded, other.number) == "Todo"


def test_partial_merge_keeps_the_task_in_progress(boarded):
    workspace = boarded.create_task("t").start()
    commit(boarded, workspace, "a.txt")
    pr = workspace.submit(partial=True)
    assert status_of(boarded, workspace.number) == "In Review"
    pr.merge()
    assert status_of(boarded, workspace.number) == "In Progress"


def test_task_without_workspace(boarded):
    task = boarded.create_task("調べる")
    started = boarded.start_task_without_workspace(task.number)
    assert started.assignees and status_of(boarded, task.number) == "In Progress"
    assert boarded.current_workspace() is None
    assert [t.number for t in boarded.tasks(ready=True)] == []   # 作業中は着手できる一覧に出ない
    boarded.close_task(task.number)
    assert status_of(boarded, task.number) == "Done"


def test_fields(boarded):
    task = boarded.create_task("t")
    assert boarded.set_task_field(task.number, "priority", "high").values["Priority"] == "High"
    boarded.set_task_field(task.number, "Due", "2026-10-20")
    boarded.set_task_field(task.number, "Estimate", "3")
    boarded.set_task_field(task.number, "Status", "Backlog")   # 計画の段階は設定できる
    listed = boarded.tasks()[0]
    assert listed.status == "Backlog" and listed.fields == {"Priority": "High", "Due": "2026-10-20", "Estimate": "3"}
    assert code_of(lambda: boarded.set_task_field(task.number, "Status", "Done")) == ErrorCode.STAGE_FIELD
    assert code_of(lambda: boarded.set_task_field(task.number, "Due", "明日")) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: boarded.set_task_field(task.number, "Estimate", "x")) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: boarded.set_task_field(task.number, "Priority", "Mid")) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: boarded.set_task_field(task.number, "Size", "S")) == ErrorCode.FIELD_NOT_FOUND
    assert "Due" not in boarded.clear_task_field(task.number, "Due").values


def test_sync_adds_tasks_and_follows_the_work(repository, boarded):
    plain = Repository(repository.root, github=repository.github, command="ecobuild")   # ボードなしで作る
    todo = plain.create_task("未着手")
    working = plain.create_task("作業中")
    plain.task(working.number).start()
    planned = boarded.create_task("計画")
    boarded.set_task_field(planned.number, "Status", "Backlog")
    assert code_of(lambda: boarded.set_task_field(todo.number, "Priority", "High")) == ErrorCode.NOT_ON_BOARD

    preview = boarded.sync_board(dry_run=True)
    assert preview.added == (todo.number, working.number) and status_of(boarded, todo.number) is None
    result = boarded.sync_board()
    assert [(c.number, c.after) for c in result.changed] == [(todo.number, "Todo"), (working.number, "In Progress")]
    assert status_of(boarded, planned.number) == "Backlog"                      # 計画の段階はそのまま
    assert boarded.sync_board().changed == ()


def test_board_failure_does_not_fail_the_operation(boarded, monkeypatch):
    def failing(*args, **kwargs):
        raise WorkError(ErrorCode.BOARD_PERMISSION, "権限がありません")

    monkeypatch.setattr(boarded.github, "set_board_value", failing)
    task = boarded.create_task("t")
    assert task.number and any("board sync" in n for n in boarded.notices)


def test_checking_board_settings(boarded):
    board = boarded.board
    assert boarded.board_status().stages == STAGES
    bad = BoardSettings(board.url, "Status", {**STAGES, "done": "Finished"})
    assert code_of(lambda: boarded.check_board(bad)) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: boarded.check_board(BoardSettings(board.url, "Priority", STAGES))) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: Repository(boarded.root, github=boarded.github).board_status()) == ErrorCode.NO_BOARD


def test_ready_tasks_are_sorted_and_exclude_planning(boarded):
    low, high, later, none = (boarded.create_task(t) for t in ("低", "高", "後で", "未設定"))
    boarded.set_task_field(low.number, "Priority", "Low")
    boarded.set_task_field(high.number, "Priority", "High")
    boarded.set_task_field(later.number, "Status", "Backlog")      # 計画中は着手できる一覧に出さない
    ready = boarded.tasks(ready=True, sort="Priority")
    assert [t.number for t in ready] == [high.number, low.number, none.number]
    assert [t.number for t in boarded.tasks(sort="Status")][0] == later.number   # 選択肢の順（Backlog が先頭）
