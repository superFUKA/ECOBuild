import pytest

from helpers import git, write
from ecowork.errors import ErrorCode, WorkError

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def test_task_start_creates_workspace(repository):
    task = repository.create_task("0除算対策", body="divide(1,0)")
    workspace = task.start()
    assert (workspace.number, workspace.branch, workspace.base) == (task.number, "task/1", "main")
    assert repository.current_workspace() == workspace
    status = repository.status()
    assert status.workspace == 1 and status.branch == "task/1" and status.pull_request is None


def test_commit_only_in_workspace(repository):
    assert repository.current_workspace() is None
    assert code_of(lambda: repository.require_workspace("コミット")) == ErrorCode.NOT_IN_WORKSPACE
    workspace = repository.create_task("t").start()
    write(repository.root / "a.cpp", "int a;\n")
    assert workspace.stage("a.cpp").staged == ("a.cpp",)
    result = workspace.commit("a を追加")
    assert result.branch == "task/1" and len(result.sha) == 40
    workspace.push()
    remote = repository.remote_url
    assert git(repository.root, "ls-remote", remote, "task/1").split()[0] == result.sha


def test_start_refuses_uncommitted_changes(repository):
    write(repository.root / "README.md", "changed\n")
    task = repository.create_task("t")
    assert code_of(task.start) == ErrorCode.DIRTY_WORKING_TREE


def test_start_from_another_branch(repository):
    develop = repository.create_branch("develop")
    assert (develop.name, develop.is_workspace, develop.local, develop.remote) == ("develop", False, True, True)
    workspace = repository.create_task("t").start(base="develop")
    assert workspace.base == "develop"
    # 別のIssueの作業空間は作業空間からは作れない
    second = repository.create_task("u")
    assert code_of(lambda: second.start(base="task/1")) == ErrorCode.INVALID_BASE


def test_resume_existing_workspace(repository):
    first = repository.create_task("t").start()
    git(repository.root, "switch", "--quiet", "main")
    again = repository.task(first.number).start()
    assert again.branch == first.branch


def test_branch_rules(repository):
    assert code_of(lambda: repository.create_branch("task/9")) == ErrorCode.RESERVED_BRANCH_NAME
    assert code_of(lambda: repository.create_branch("x", base="nothing")) == ErrorCode.BRANCH_NOT_FOUND
    repository.create_branch("develop")
    assert code_of(lambda: repository.create_branch("develop")) == ErrorCode.ALREADY_EXISTS
    assert code_of(lambda: repository.branch("main").delete()) == ErrorCode.PROTECTED_BRANCH
    repository.create_task("t").start(base="develop")
    assert code_of(lambda: repository.branch("develop").delete()) == ErrorCode.PROTECTED_BRANCH
    assert code_of(lambda: repository.branch("task/1").delete()) == ErrorCode.PROTECTED_BRANCH
    repository.create_branch("release")
    repository.branch("release").delete()
    names = {b.name for b in repository.branches()}
    assert "release" not in names and {"main", "develop", "task/1"} <= names


def test_closed_task_cannot_start(repository):
    task = repository.create_task("t")
    repository.github.close_issue(repository.root, task.number)
    assert code_of(repository.task(task.number).start) == ErrorCode.TASK_CLOSED


def test_commit_without_staged_changes(repository):
    from helpers import write
    workspace = repository.create_task("t").start()
    assert code_of(lambda: workspace.commit("空")) == ErrorCode.NOTHING_TO_COMMIT
    write(repository.root / "README.md", "changed\n")
    assert code_of(lambda: workspace.commit("未ステージ")) == ErrorCode.NOTHING_TO_COMMIT
    workspace.commit("追跡中の変更", all=True)
    workspace.commit("やり直し", amend=True)  # 変更がなくても書き換えはできる


def test_status_reports_deleted_upstream(repository, remote_and_clone):
    """別の場所で作業空間のGitHubのブランチが消された（task drop等）ことを status で示す。"""
    remote, _ = remote_and_clone
    workspace = repository.create_task("t").start()
    write(repository.root / "a.txt", "a\n")
    workspace.stage("a.txt")
    workspace.commit("a")
    workspace.push()
    assert not repository.status().upstream_gone
    git(remote, "branch", "-D", "task/1")
    repository.git.fetch()
    assert repository.status().upstream_gone


def test_start_existing_workspace_fast_forwards(repository, remote_and_clone, tmp_path):
    """手元に古い作業空間があるとき、task start で別の場所からpushされた続きを取り込む。"""
    remote, _ = remote_and_clone
    workspace = repository.create_task("t").start()
    write(repository.root / "a.txt", "a\n")
    workspace.stage("a.txt")
    workspace.commit("a")
    workspace.push()
    other = tmp_path / "other"
    git(tmp_path, "clone", "--quiet", "--branch", "task/1", str(remote), str(other))
    write(other / "b.txt", "b\n")
    git(other, "add", "b.txt")
    git(other, "commit", "--quiet", "-m", "b")
    git(other, "push", "--quiet", "origin", "task/1")
    repository.task(1).start()
    assert (repository.root / "b.txt").exists()


def test_clone_repository(repository, tmp_path):
    from ecowork import Repository
    target = tmp_path / "second"
    target.mkdir()
    cloned = Repository.clone("remote", directory=target, github=repository.github, command="ecobuild")
    assert cloned.root == (target / "remote").resolve() and (cloned.root / "README.md").exists()
    assert cloned.status().branch == "main"
    assert code_of(lambda: Repository.clone("remote", directory=target, github=repository.github)) \
        == ErrorCode.ALREADY_EXISTS
    assert code_of(lambda: Repository.clone("nosuch", directory=target, github=repository.github)) \
        == ErrorCode.REPOSITORY_NOT_FOUND
