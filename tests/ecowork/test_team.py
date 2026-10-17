"""複数人での開発：担当者の確認と引き継ぎ・共同作業者・ブランチの保護。"""

import pytest

from helpers import write
from ecowork.errors import ErrorCode, WorkError

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def test_start_stops_on_someone_elses_task_and_take_over(repository):
    task = repository.create_task("他の人の", assignees=("alice",))
    with pytest.raises(WorkError) as error:
        task.start()
    assert error.value.code == ErrorCode.ASSIGNED_TO_OTHER and "--take-over" in error.value.hint
    assert not repository.git.has_local_branch(f"task/{task.number}")
    task_branch = repository.task(task.number).start(take_over=True)
    assert task_branch.number == task.number
    assert repository.task(task.number).assignees == ("tester",)
    comments = repository.github.comments[task.number]
    assert "引き継ぎました" in comments[-1].body and "alice" in comments[-1].body
    assert any("引き継ぎました" in n for n in repository.notices)


def test_start_is_fine_when_unassigned_or_shared(repository):
    unassigned = repository.create_task("担当なし")
    unassigned.start()
    assert repository.task(unassigned.number).assignees == ("tester",)
    shared = repository.create_task("2人で", assignees=("alice", "@me"))
    repository.git.switch("main")
    shared.start()                                       # 自分が担当者の1人なら止めない
    assert set(repository.task(shared.number).assignees) == {"alice", "tester"}


def test_no_workspace_start_checks_the_assignee(repository):
    task = repository.create_task("調べる", assignees=("alice",))
    assert code_of(lambda: repository.start_task_without_branch(task.number)) == ErrorCode.ASSIGNED_TO_OTHER
    repository.start_task_without_branch(task.number, take_over=True)
    assert repository.task(task.number).assignees == ("tester",)


def test_members_invite_accept_and_remove(repository):
    github = repository.github
    assert repository.add_member("@alice")                # 招待を送った
    assert code_of(lambda: repository.add_member("bob", "owner")) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: repository.add_member("tester")) == ErrorCode.INVALID_ARGUMENT
    assert [(m.login, m.role, m.invited) for m in repository.members()] == [("alice", "write", True)]
    github.accept_invitation("alice")
    assert [(m.login, m.invited) for m in repository.members()] == [("alice", False)]
    assert not repository.add_member("alice", "read")     # 既に共同作業者：役割を変える
    assert github.collaborator_roles["alice"] == "read"
    assert repository.remove_member("alice")
    assert code_of(lambda: repository.remove_member("alice")) == ErrorCode.INVALID_ARGUMENT


def test_members_share_the_task_data(repository):
    github = repository.github
    repository.create_task("ボードを作る")                 # ボードはタスクを初めて記録したときにできる
    repository.add_member("alice")
    github.accept_invitation("alice")
    repository.members()
    board = github.ecobuild_board()
    assert github.shared_boards[board.id] == ("alice",)


def test_protect_the_base_branch(repository):
    from ecowork.github import RunInfo
    github = repository.github
    assert repository.protection() is None
    protection = repository.protect(approvals=1)
    assert (protection.branch, protection.approvals, protection.checks) == ("main", 1, ())
    assert repository.protection() == protection
    assert code_of(lambda: repository.protect(require_ci=True)) == ErrorCode.NO_CI_RUN
    github.runs = [RunInfo(1, "build", "main", "push", "completed", "success", "u", "t")]
    assert repository.protect(require_ci=True).checks == ("build",)
    assert code_of(lambda: repository.protect(branch="task/1")) == ErrorCode.INVALID_BASE
    assert code_of(lambda: repository.protect(approvals=7)) == ErrorCode.INVALID_ARGUMENT
    assert repository.unprotect() and not repository.unprotect()
    github.free_private = True
    assert code_of(lambda: repository.protect()) == ErrorCode.PLAN_REQUIRED


def test_finish_explains_a_branch_policy(repository, monkeypatch):
    """GitHub のブランチの保護に止められたら、承認を案内する。"""
    github = repository.github
    task_branch = repository.create_task("t").start()
    write(repository.root / "a.txt", "a\n")
    task_branch.record("a")

    def refused(*args, **kwargs):
        raise WorkError(ErrorCode.APPROVAL_REQUIRED, "PR は取り込めません。")

    monkeypatch.setattr(github, "merge_pull_request", refused)
    with pytest.raises(WorkError) as error:
        repository.finish()
    assert error.value.code == ErrorCode.APPROVAL_REQUIRED and f"task approve {task_branch.number}" in error.value.hint
