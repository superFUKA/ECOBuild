"""タスクの反映（task apply：提出を通さずに作成元へ）。できるのは作成元への提出を処理できる人だけ。"""

import pytest

from helpers import git, write
from ecowork.errors import ErrorCode, WorkError

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def as_role(repository, role, **creators):
    repository.github.role = role
    repository.github.branch_creators_.update(creators)
    repository._access = repository._creators = None


def started(repository, title="t", **options):
    task = repository.create_task(title)
    return task, task.start(**options)


def test_apply_squashes_into_the_base_without_a_submission(repository):
    """提出（PR）を作らずに、作成元の最新へ1つのコミットで入れ、Issueを閉じ、タスクブランチを片付ける。"""
    task, task_branch = started(repository, "反映する")
    write(repository.root / "a.txt", "a\n")
    task_branch.record("a")
    write(repository.root / "b.txt", "b\n")
    task_branch.record("b")   # 未pushのコミットも入る
    result = repository.apply_task()
    assert result.task == task.number and result.base == "main" and result.commit and result.method == "squash"
    assert result.removed and result.switched_to == "main" and result.closed_submission is None
    assert repository.github.pulls == {}                                   # 提出は作らない
    assert repository.task(task.number).state == "closed"
    assert not repository.git.has_local_branch(task_branch.branch)        # 失われるコミットとみなさずに片付ける
    assert not repository.git.has_remote_branch(task_branch.branch)
    assert git(repository.root, "log", "-1", "--format=%s") == f"反映する (タスク #{task.number})"
    assert git(repository.root, "rev-list", "--count", "origin/main^..origin/main") == "1"   # スカッシュ（親は1つ）
    assert (repository.root / "a.txt").exists() and (repository.root / "b.txt").exists()
    entry = repository.log(count=1)[0]
    assert (entry.pull_request, entry.issue) == (None, task.number)


def test_apply_closes_an_open_submission_and_uses_the_subject(repository):
    task, task_branch = started(repository)
    write(repository.root / "a.txt", "a\n")
    task_branch.record("a")
    pr = task_branch.submit()
    repository.git.switch("main")
    result = repository.apply_task(task.number, subject="中身に合った件名")
    assert result.closed_submission == pr.number and repository.github.pulls[pr.number].state == "closed"
    assert git(repository.root, "log", "-1", "--format=%s", "origin/main") == f"中身に合った件名 (タスク #{task.number})"


def test_apply_merges_onto_a_base_that_moved(repository):
    """作成元が先へ進んでいても、衝突しなければ作成元の最新の上に入れる。"""
    first, first_branch = started(repository, "先")
    second, second_branch = started(repository, "後")
    write(repository.root / "b.txt", "b\n")
    second_branch.record("b")
    repository.git.switch(first_branch.branch)
    write(repository.root / "a.txt", "a\n")
    first_branch.record("a")
    repository.apply_task(first.number)
    result = repository.apply_task(second.number)
    assert result.commit
    tree = git(repository.root, "ls-tree", "--name-only", "origin/main")
    assert "a.txt" in tree and "b.txt" in tree


def test_apply_refuses_conflicts_and_nothing_to_apply(repository):
    first, first_branch = started(repository, "先")
    assert code_of(repository.apply_task) == ErrorCode.NOTHING_TO_SUBMIT
    second, second_branch = started(repository, "後")
    write(repository.root / "README.md", "後\n")
    second_branch.record("後")
    repository.git.switch(first_branch.branch)
    write(repository.root / "README.md", "先\n")
    first_branch.record("先")
    repository.apply_task(first.number)
    before = git(repository.root, "rev-parse", "origin/main")
    error = pytest.raises(WorkError, repository.apply_task, second.number).value
    assert error.code == ErrorCode.MERGE_CONFLICT and "README.md" in error.details and "sync" in error.hint
    assert git(repository.root, "rev-parse", "origin/main") == before      # 何も変えない
    assert repository.task(second.number).state == "open"


def test_apply_completes_when_the_changes_are_already_in(repository):
    """コミットはあるが、同じ中身が別のタスクで作成元に入っている：入れずに完了し、タスクブランチも片付ける。"""
    first, first_branch = started(repository, "先")
    second, second_branch = started(repository, "後")
    write(repository.root / "a.txt", "a\n")
    second_branch.record("a")
    second_branch.push()
    repository.git.switch(first_branch.branch)
    write(repository.root / "a.txt", "a\n")
    first_branch.record("同じ変更")
    repository.apply_task(first.number)
    before = git(repository.root, "rev-parse", "origin/main")
    result = repository.apply_task(second.number)
    assert (result.commit, result.method) == (None, "up-to-date") and result.removed
    assert git(repository.root, "rev-parse", "origin/main") == before      # 何も入れない
    assert repository.task(second.number).state == "closed"
    assert not repository.git.has_local_branch(second_branch.branch)
    assert not repository.git.has_remote_branch(second_branch.branch)


def absorbed(repository):
    """同じ変更を、別のタスク（先）で作成元へ入れた後のタスク（後）。後のコミットは作成元にない。"""
    first, first_branch = started(repository, "先")
    second, second_branch = started(repository, "後")
    write(repository.root / "a.txt", "a\n")
    second_branch.record("a")
    second_branch.push()
    repository.git.switch(first_branch.branch)
    write(repository.root / "a.txt", "a\n")
    first_branch.record("同じ変更")
    repository.apply_task(first.number)
    return second, second_branch


def test_a_task_whose_changes_are_in_closes_as_completed(repository):
    """閉じる（task close）・片付け（prune）も、反映と同じ判断：中身が作成元にあれば失われる変更はない。"""
    second, second_branch = absorbed(repository)
    assert repository.close_task(second.number).state == "closed"
    assert second.number not in repository.github.not_planned              # 捨てたのではなく「完了」
    assert not repository._lost_commits(second_branch.branch, "main", local=True, remote=True)


def test_apply_resumes_after_closing_a_task_whose_changes_are_in(repository):
    """入れずに完了する途中（Issue を閉じた後）で止まっても、もう一度の反映で片付けの残りを行う。"""
    second, second_branch = absorbed(repository)
    repository.github.close_issue(repository.root, second.number)
    result = repository.apply_task(second.number)
    assert result.commit is None and not repository.git.has_remote_branch(second_branch.branch)


def test_apply_is_for_those_who_handle_the_base(repository):
    """作成元を作った人と管理者だけ。既定のブランチは管理者だけ。承認が必須のモジュールでは使えない。"""
    repository.create_branch("develop")
    as_role(repository, "write", develop="tester")
    task, task_branch = started(repository, "develop へ", base="develop")
    write(repository.root / "a.txt", "a\n")
    task_branch.record("a")
    assert repository.apply_task().base == "develop"                       # develop を作ったのは自分
    other, other_branch = started(repository, "main へ")
    write(repository.root / "b.txt", "b\n")
    other_branch.record("b")
    error = pytest.raises(WorkError, repository.apply_task).value
    assert error.code == ErrorCode.PERMISSION_DENIED and "管理者" in error.message
    as_role(repository, "admin")
    repository.require_approval = True
    assert code_of(repository.apply_task) == ErrorCode.APPROVAL_REQUIRED
    repository.require_approval = False
    assert repository.apply_task().task == other.number


def test_apply_a_subtask_into_the_parent_task_branch(repository):
    """子タスクは親のタスクブランチへ。親のタスクブランチを作った人が反映できる。"""
    parent = repository.create_task("親")
    child = repository.create_task("子", parent=parent.number)
    task_branch = repository.task(child.number).start()
    parent_branch = task_branch.base
    as_role(repository, "write", **{parent_branch: "tester"})
    write(repository.root / "a.txt", "a\n")
    task_branch.record("a")
    result = repository.apply_task()
    assert result.base == parent_branch and repository.task(child.number).state == "closed"
    tree = git(repository.root, "ls-tree", "--name-only", f"origin/{parent_branch}")
    assert "a.txt" in tree
    as_role(repository, "write", **{parent_branch: "alice"})
    second = repository.create_task("子2", parent=parent.number)
    second_branch = repository.task(second.number).start()
    write(repository.root / "b.txt", "b\n")
    second_branch.record("b")
    assert code_of(repository.apply_task) == ErrorCode.PERMISSION_DENIED


def test_apply_again_after_it_stopped_does_only_the_rest(repository):
    """push の後で止まっても、もう一度実行すると後処理の残りだけを行う（同じ変更を二度入れない）。"""
    task, task_branch = started(repository)
    write(repository.root / "a.txt", "a\n")
    task_branch.record("a")
    task_branch.push()
    close = repository.github.close_issue
    repository.github.close_issue = lambda *a: (_ for _ in ()).throw(WorkError(ErrorCode.GIT_ERROR, "止まった"))
    assert code_of(repository.apply_task) == ErrorCode.GIT_ERROR
    applied = git(repository.root, "rev-parse", "origin/main")
    repository.github.close_issue = close
    result = repository.apply_task(task.number)
    assert result.commit is None and result.method == "up-to-date" and result.removed
    assert git(repository.root, "rev-parse", "origin/main") == applied
    assert repository.task(task.number).state == "closed"
    assert code_of(lambda: repository.apply_task(task.number)) == ErrorCode.TASK_CLOSED   # 片付いた後
