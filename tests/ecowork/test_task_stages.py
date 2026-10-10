"""作業の段階・計画の値（内部ではボードに置く）と、作業の流れの連動。偽のGitHub＋手元のbareで確かめる。"""

import pytest

from helpers import write
from ecowork.errors import ErrorCode, WorkError

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def stage_of(repo, number):
    return repo.task_status(number).task.stage


def commit(repo, workspace, name):
    write(repo.root / name, "x\n")
    workspace.stage(name)
    workspace.commit(name)


def set_status(repo, number, option):
    """GitHubのサイトで状態を変えた（ECOBuildを通さない）。"""
    store = repo.tracker.store
    store.write(store.item(number), store.info().field("Status"), option)


def test_stages_follow_the_work(repository):
    task = repository.create_task("t")
    assert stage_of(repository, task.number) == "todo"
    workspace = task.start()
    assert stage_of(repository, task.number) == "in_progress"
    commit(repository, workspace, "a.txt")
    pr = workspace.submit(draft=True)
    assert stage_of(repository, task.number) == "in_progress"      # 下書きは作業中のまま
    repository.set_pull_request_draft(pr.number, draft=False)
    assert stage_of(repository, task.number) == "in_review"
    repository.close_pull_request(pr.number)
    assert stage_of(repository, task.number) == "in_progress"
    repository.reopen_pull_request(pr.number)
    assert stage_of(repository, task.number) == "in_review"
    repository.pull_request(pr.number).merge()
    assert stage_of(repository, task.number) == "done"
    assert repository.notices == []

    other = repository.create_task("やめる")
    other.start()
    repository.drop_workspace(other.number)
    assert stage_of(repository, other.number) == "todo"
    repository.close_task(other.number)
    assert stage_of(repository, other.number) == "done"
    repository.reopen_task(other.number)
    assert stage_of(repository, other.number) == "todo"


def test_partial_merge_keeps_the_task_in_progress(repository):
    workspace = repository.create_task("t").start()
    commit(repository, workspace, "a.txt")
    pr = workspace.submit(partial=True)
    assert stage_of(repository, workspace.number) == "in_review"
    pr.merge()
    assert stage_of(repository, workspace.number) == "in_progress"


def test_task_without_workspace(repository):
    task = repository.create_task("調べる")
    started = repository.start_task_without_workspace(task.number)
    assert started.assignees and stage_of(repository, task.number) == "in_progress"
    assert repository.current_workspace() is None
    assert [t.number for t in repository.tasks(ready=True)] == []   # 作業中は着手できる一覧に出ない
    repository.close_task(task.number)
    assert stage_of(repository, task.number) == "done"


def test_list_fixes_stages_changed_outside(repository):
    """GitHubのサイトでの操作（閉じる・作業空間を作る等）でずれた段階は、一覧のときに直す。計画中は変えない。"""
    closed, working, planned = (repository.create_task(t) for t in ("閉じた", "作業中", "計画"))
    repository.task(working.number).start()
    repository.git.run("switch", "--quiet", "main")
    set_status(repository, working.number, "Todo")                 # 記録に失敗した等でずれた
    set_status(repository, planned.number, "Backlog")
    repository.github.close_issue(repository.root, closed.number)
    listed = {t.number: t.stage for t in repository.tasks(closed=True)}
    assert listed == {closed.number: "done", working.number: "in_progress", planned.number: "planned"}
    assert stage_of(repository, working.number) == "in_progress"


def test_recording_failure_does_not_fail_the_operation(repository, monkeypatch):
    def failing(*args, **kwargs):
        raise WorkError(ErrorCode.BOARD_PERMISSION, "権限がありません")

    monkeypatch.setattr(repository.github, "set_board_value", failing)
    task = repository.create_task("t")
    assert task.number and any("task list" in n for n in repository.notices)


def test_ready_tasks_are_sorted_and_exclude_planning(repository):
    low, high, later, none = (repository.create_task(t) for t in ("低", "高", "後で", "未設定"))
    repository.plan_task(low.number, priority="Low")
    repository.plan_task(high.number, priority="High")
    set_status(repository, later.number, "Backlog")                 # 計画中は着手できる一覧に出さない
    ready = repository.tasks(ready=True, sort="priority")
    assert [t.number for t in ready] == [high.number, low.number, none.number]
    assert code_of(lambda: repository.tasks(sort="Status")) == ErrorCode.INVALID_ARGUMENT


def test_listed_tasks_show_no_storage_details(repository):
    """一覧・詳細に、置き場所（ボード）の生の値は出さない。"""
    task = repository.create_task("t")
    listed = repository.tasks()[0]
    assert not hasattr(listed, "status") and not hasattr(listed, "fields") and listed.stage == "todo"
    assert not hasattr(repository.task_status(task.number), "board")
