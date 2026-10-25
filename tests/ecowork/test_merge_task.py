"""ブランチ同士の衝突を直すタスク（branch resolve）：取り込み先をタスクブランチへ取り込んで直し、作成元へ履歴ごと入れる。"""

import pytest

from helpers import git, write
from ecowork.errors import ErrorCode, WorkError

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def changed_on(repository, branch, text, title):
    """管理用のブランチ branch の README.md を text にする（タスクで入れる）。"""
    task = repository.create_task(title)
    task_branch = task.start(base=branch)
    write(repository.root / "README.md", text)
    task_branch.record(title)
    repository.apply_task()


@pytest.fixture
def diverged(repository):
    """dev と main が同じ所を別々に変えた（dev → main が衝突する）。"""
    repository.create_branch("dev")
    changed_on(repository, "dev", "dev\n", "dev の変更")
    changed_on(repository, "main", "main\n", "main の変更")
    assert repository.plan_branch_merge("dev", "main").method == "conflict"
    return repository


def started_fix(repository):
    task = repository.create_merge_task("dev", "main")
    task_branch = repository.task(task.number).start(base="dev", name="fix")
    assert task_branch.base == "dev"
    with pytest.raises(WorkError) as error:
        repository.sync()                                   # main も取り込む：衝突で止まる
    assert error.value.code == ErrorCode.MERGE_CONFLICT and "README.md" in error.value.details
    write(repository.root / "README.md", "dev と main\n")
    repository.continue_sync()
    return task


def test_the_fix_is_applied_with_its_history_and_the_merge_becomes_a_fast_forward(diverged):
    repository = diverged
    task = started_fix(repository)
    result = repository.apply_task()
    assert result.base == "dev" and result.removed and repository.task(task.number).state == "closed"
    assert not repository.git.has_remote_branch(f"task/{task.number}-fix")
    assert repository.git.is_ancestor("origin/main", "origin/dev")              # スカッシュしない：main を含む
    assert repository.plan_branch_merge("dev", "main").method == "fast-forward"
    repository.merge_branch_into("dev", "main")
    assert git(repository.root, "show", "origin/main:README.md") == "dev と main"


def test_the_fix_taken_in_by_a_submission_keeps_its_history_too(diverged):
    repository = diverged
    started_fix(repository)
    repository.finish()
    assert repository.git.is_ancestor("origin/main", "origin/dev")
    assert repository.plan_branch_merge("dev", "main").method in ("fast-forward", "merge")


def test_a_fix_task_is_only_for_a_conflict(repository):
    repository.create_branch("dev")
    changed_on(repository, "dev", "dev\n", "dev の変更")
    assert code_of(lambda: repository.create_merge_task("dev", "main")) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: repository.create_merge_task("task/1-x", "main")) == ErrorCode.PROTECTED_BRANCH
