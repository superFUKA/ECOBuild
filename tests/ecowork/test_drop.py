import pytest

from helpers import git, write
from ecowork.errors import ErrorCode, WorkError

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def commit_file(workspace, root, name, text, message):
    write(root / name, text)
    workspace.stage(name)
    return workspace.commit(message)


def test_drop_current_workspace_with_pull_request(repository):
    root, github = repository.root, repository.github
    repository.create_branch("develop")
    workspace = repository.create_task("やめる作業").start(base="develop")
    commit_file(workspace, root, "a.txt", "a\n", "途中")
    pr = workspace.submit()

    preview = repository.drop_workspace(dry_run=True)
    assert preview.lost_commits == ("途中",) and preview.closed_pull_requests == (pr.number,)
    assert preview.switched_to == "develop" and git(root, "branch", "--show-current") == "task/1"
    # GitHubにpush済みでも、GitHubのブランチも消すため失われる
    assert code_of(repository.drop_workspace) == ErrorCode.COMMITS_WOULD_BE_LOST

    result = repository.drop_workspace(discard=True)
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
    result = repository.drop_workspace(close=True)
    assert result.lost_commits == () and result.issue_closed and result.switched_to == "main"
    assert repository.github.issues[1].state == "closed" and 1 in repository.github.not_planned


def test_drop_other_workspace_by_number(repository):
    root = repository.root
    first = repository.create_task("1つ目").start()
    commit_file(first, root, "a.txt", "a\n", "1つ目の作業")
    git(root, "switch", "--quiet", "main")
    repository.create_task("2つ目").start()
    result = repository.drop_workspace(1, discard=True)
    assert result.switched_to is None and result.lost_commits == ("1つ目の作業",)
    assert git(root, "branch", "--show-current") == "task/2"
    assert not repository.git.has_local_branch("task/1")


def test_drop_refusals(repository):
    root = repository.root
    assert code_of(repository.drop_workspace) == ErrorCode.NOT_IN_WORKSPACE
    assert code_of(lambda: repository.drop_workspace(9)) == ErrorCode.BRANCH_NOT_FOUND
    repository.create_task("t").start()
    write(root / "README.md", "changed\n")
    assert code_of(repository.drop_workspace) == ErrorCode.DIRTY_WORKING_TREE


def test_drop_after_partial_merge_loses_only_the_rest(repository):
    root = repository.root
    workspace = repository.create_task("大きな作業").start()
    commit_file(workspace, root, "a.txt", "1\n", "前半")
    workspace.submit(partial=True).merge()
    commit_file(workspace, root, "b.txt", "2\n", "続き")
    assert repository.drop_workspace(dry_run=True).lost_commits == ("続き",)
