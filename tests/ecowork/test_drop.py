import pytest

from helpers import git, write
from ecowork.errors import ErrorCode, WorkError

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def commit_file(task_branch, root, name, text, message):
    write(root / name, text)
    task_branch.stage(name)
    return task_branch.commit(message)


def test_drop_current_workspace_with_pull_request(repository):
    root, github = repository.root, repository.github
    repository.create_branch("develop")
    task_branch = repository.create_task("やめる作業").start(base="develop")
    commit_file(task_branch, root, "a.txt", "a\n", "途中")
    pr = task_branch.submit()

    preview = repository.drop_task(dry_run=True)
    assert preview.lost_commits == ("途中",) and preview.closed_pull_requests == (pr.number,)
    assert preview.switched_to == "develop" and git(root, "branch", "--show-current") == "task/1"
    # GitHubにpush済みでも、GitHubのブランチも消すため失われる
    assert code_of(repository.drop_task) == ErrorCode.COMMITS_WOULD_BE_LOST

    result = repository.drop_task(discard=True)
    assert (result.branch, result.switched_to, result.issue_closed) == ("task/1", "develop", False)
    assert github.pulls[pr.number].state == "closed"
    assert github.issues[1].state == "open"
    assert git(root, "branch", "--show-current") == "develop"
    assert not repository.git.has_local_branch("task/1") and not repository.git.has_remote_branch("task/1")
    assert repository.git.get_config("branch.task/1.ecowork-base") is None
    # Issueは開いたままなので、作成元の最新から作り直せる
    again = repository.task(1).start()
    assert again.branch == "task/1" and not (root / "a.txt").exists()


def test_drop_without_commits_needs_no_confirmation_and_can_close_issue(repository):
    repository.create_task("不要になった").start()
    result = repository.drop_task(close=True)
    assert result.lost_commits == () and result.issue_closed and result.switched_to == "main"
    assert repository.github.issues[1].state == "closed" and 1 in repository.github.not_planned


def test_drop_other_workspace_by_number(repository):
    root = repository.root
    first = repository.create_task("1つ目").start()
    commit_file(first, root, "a.txt", "a\n", "1つ目の作業")
    git(root, "switch", "--quiet", "main")
    repository.create_task("2つ目").start()
    result = repository.drop_task(1, discard=True)
    assert result.switched_to is None and result.lost_commits == ("1つ目の作業",)
    assert git(root, "branch", "--show-current") == "task/2"
    assert not repository.git.has_local_branch("task/1")


def test_drop_refusals(repository):
    root = repository.root
    assert code_of(repository.drop_task) == ErrorCode.NOT_ON_TASK_BRANCH
    assert code_of(lambda: repository.drop_task(9)) == ErrorCode.BRANCH_NOT_FOUND
    repository.create_task("t").start()
    write(root / "README.md", "changed\n")
    assert code_of(repository.drop_task) == ErrorCode.DIRTY_WORKING_TREE


def test_drop_after_partial_merge_loses_only_the_rest(repository):
    root = repository.root
    task_branch = repository.create_task("大きな作業").start()
    commit_file(task_branch, root, "a.txt", "1\n", "前半")
    task_branch.submit(partial=True).merge()
    commit_file(task_branch, root, "b.txt", "2\n", "続き")
    assert repository.drop_task(dry_run=True).lost_commits == ("続き",)


def test_drop_close_unstarted_issue(repository):
    """タスクブランチのない（開始していない）Issueも --close で「対応しない」として閉じられる。"""
    task = repository.create_task("やめる")
    assert code_of(lambda: repository.drop_task(task.number)) == ErrorCode.BRANCH_NOT_FOUND
    result = repository.drop_task(task.number, close=True)
    assert result.issue_closed and result.lost_commits == ()
    assert repository.github.issues[task.number].state == "closed" and task.number in repository.github.not_planned
