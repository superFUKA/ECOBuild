"""タスクブランチの名前（task/<番号>-<名前>）。日本語も使え、新しく作るときは名前を必ず入れてもらえる（空なら止める）。"""

import pytest

from helpers import write
from ecowork import model as wm
from ecowork.errors import ErrorCode, WorkError

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def test_label_from_title_and_check():
    assert wm.branch_label("ログイン画面を作る") == "ログイン画面を作る"
    assert wm.branch_label("  設定: 読み込み/保存 [v2]? ") == "設定-読み込み-保存-v2"
    assert wm.branch_label("a..b.lock") == "a-b"
    assert wm.branch_label("???") == ""
    assert wm.check_branch_label(" ログイン画面 ") == "ログイン画面"
    assert code_of(lambda: wm.check_branch_label("")) == ErrorCode.BRANCH_NAME_REQUIRED
    assert code_of(lambda: wm.check_branch_label("ログイン 画面")) == ErrorCode.INVALID_BRANCH_NAME
    assert wm.task_number("task/12-ログイン画面") == 12 and wm.task_number("task/12") == 12
    assert wm.task_number("task/ログイン") is None


def test_start_with_japanese_name(repository):
    task = repository.create_task("ログイン画面を作る")
    assert code_of(lambda: task.start(name="ログイン 画面")) == ErrorCode.INVALID_BRANCH_NAME
    with pytest.raises(WorkError) as error:
        task.start(name="")                                   # 名前は必須（題名から作った例を案内する）
    assert error.value.code == ErrorCode.BRANCH_NAME_REQUIRED and "--name ログイン画面を作る" in error.value.hint
    assert not repository.git.has_local_branch("task/1")

    task_branch = task.start(name="ログイン画面")
    assert task_branch.branch == "task/1-ログイン画面" and task_branch.number == 1
    assert repository.git.has_remote_branch("task/1-ログイン画面")
    assert "branch: task/1-ログイン画面" in repository.github.issues[1].body   # 名前もIssueに残す
    assert repository.task_status(1).branch == "task/1-ログイン画面"
    assert [t.branch for t in repository.tasks()] == ["task/1-ログイン画面"]
    assert task.start(name="").branch == "task/1-ログイン画面"     # 既にあれば名前は要らない


def test_restart_uses_recorded_name(repository):
    """手元もGitHubのブランチも消えていても、Issueに記録した名前で作り直す。"""
    task = repository.create_task("消して作り直す")
    task.start(name="作り直す")
    repository.remove_task_branch()
    repository.git.push_delete("task/1-作り直す")
    repository.git.fetch()
    assert task.start(name="").branch == "task/1-作り直す"


def test_submit_and_finish_named_branch(repository):
    task = repository.create_task("名前付きで完了")
    task_branch = task.start(name="名前付き")
    write(repository.root / "a.txt", "a\n")
    task_branch.record("a")
    assert task_branch.submit().head == "task/1-名前付き"
    assert repository.submission(1) is not None
    result = repository.finish()
    assert result.closed_issue == 1 and result.removed
    assert not repository.git.has_remote_branch("task/1-名前付き")
    revert = repository.revert_task(1)                         # 完了後も、記録した名前で提出を探せる
    assert revert.pull_request == result.pull_request and revert.branch.startswith(f"task/{revert.task}-")
