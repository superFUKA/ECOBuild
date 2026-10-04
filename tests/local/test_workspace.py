import pytest

from helpers import git, write
from ecobuild.errors import EcoBuildError, ErrorCode

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(EcoBuildError) as error:
        action()
    return error.value.code


def test_task_start_creates_workspace(module):
    task = module.create_task("0除算対策", body="divide(1,0)")
    workspace = task.start()
    assert (workspace.number, workspace.branch, workspace.base) == (task.number, "task/1", "main")
    assert module.current_workspace() == workspace
    status = module.status()
    assert status.workspace == 1 and status.branch == "task/1" and status.pull_request is None


def test_commit_only_in_workspace(module):
    assert module.current_workspace() is None
    assert code_of(lambda: module.require_workspace("コミット")) == ErrorCode.NOT_IN_WORKSPACE
    workspace = module.create_task("t").start()
    write(module.root / "a.cpp", "int a;\n")
    assert workspace.stage("a.cpp").staged == ("a.cpp",)
    result = workspace.commit("a を追加")
    assert result.branch == "task/1" and len(result.sha) == 40
    workspace.push()
    remote = module.remote_url
    assert git(module.root, "ls-remote", remote, "task/1").split()[0] == result.sha


def test_start_refuses_uncommitted_changes(module):
    write(module.root / "README.md", "changed\n")
    task = module.create_task("t")
    assert code_of(task.start) == ErrorCode.DIRTY_WORKING_TREE


def test_start_from_another_branch(module):
    develop = module.create_branch("develop")
    assert (develop.name, develop.is_workspace, develop.local, develop.remote) == ("develop", False, True, True)
    workspace = module.create_task("t").start(base="develop")
    assert workspace.base == "develop"
    # 別のIssueの作業空間は作業空間からは作れない
    second = module.create_task("u")
    assert code_of(lambda: second.start(base="task/1")) == ErrorCode.INVALID_BASE


def test_resume_existing_workspace(module):
    first = module.create_task("t").start()
    git(module.root, "switch", "--quiet", "main")
    again = module.task(first.number).start()
    assert again.branch == first.branch


def test_branch_rules(module):
    assert code_of(lambda: module.create_branch("task/9")) == ErrorCode.RESERVED_BRANCH_NAME
    assert code_of(lambda: module.create_branch("x", base="nothing")) == ErrorCode.BRANCH_NOT_FOUND
    module.create_branch("develop")
    assert code_of(lambda: module.create_branch("develop")) == ErrorCode.ALREADY_EXISTS
    assert code_of(lambda: module.branch("main").delete()) == ErrorCode.PROTECTED_BRANCH
    module.create_task("t").start(base="develop")
    assert code_of(lambda: module.branch("develop").delete()) == ErrorCode.PROTECTED_BRANCH
    assert code_of(lambda: module.branch("task/1").delete()) == ErrorCode.PROTECTED_BRANCH
    module.create_branch("release")
    module.branch("release").delete()
    names = {b.name for b in module.branches()}
    assert "release" not in names and {"main", "develop", "task/1"} <= names


def test_closed_task_cannot_start(module):
    task = module.create_task("t")
    module._github.close_issue(module.root, task.number)
    assert code_of(module.task(task.number).start) == ErrorCode.TASK_NOT_FOUND
