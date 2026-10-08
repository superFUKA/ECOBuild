"""PRの処理（本文の書き換え・マージの判断と後処理の再開・CIの結果の判定）。CODE_REVIEW.md の再現ケースを残す。"""

from dataclasses import replace

import pytest

from helpers import write
from ecowork import Hooks, Repository
from ecowork import github as _github
from ecowork.errors import ErrorCode, WorkError
from ecowork.github import Check, PullRequestActivity, RunInfo

pytestmark = pytest.mark.local


def code_of(action):
    with pytest.raises(WorkError) as error:
        action()
    return error.value.code


def submitted(repository, *, partial=False, name="a.txt", base=None):
    workspace = repository.create_task("t").start(base=base)
    write(repository.root / name, "a\n")
    workspace.stage(name)
    workspace.commit("a")
    return workspace, workspace.submit(partial=partial)


def body_of(repository, number):
    return repository.github.get_pull_request(repository.root, number).body


def test_editing_body_keeps_link_to_own_issue(repository):
    """別のIssueへの言及が先にあっても、そのPRのIssueとのつながり（途中の反映）を残す。"""
    workspace, pr = submitted(repository, partial=True)
    github = repository.github
    github.pulls[pr.number] = replace(github.pulls[pr.number], body=f"Closes #3\nRefs #{workspace.number}\n")
    edited = repository.edit_pull_request(pr.number, body="説明")
    assert edited.partial and f"Refs #{workspace.number}" in body_of(repository, pr.number)
    assert repository.pull_request(pr.number).merge().closed_issue is None  # 途中の反映のまま
    assert repository.task(workspace.number).state == "open"
    assert repository.git.has_remote_branch(workspace.branch)


def test_body_can_be_cleared(repository):
    workspace, pr = submitted(repository)
    assert code_of(lambda: repository.edit_pull_request(pr.number)) == ErrorCode.INVALID_ARGUMENT
    assert code_of(lambda: repository.edit_pull_request(pr.number, title=" ")) == ErrorCode.INVALID_ARGUMENT
    # 作業空間のPR：説明を消しても、Issueとのつながりは残る
    repository.edit_pull_request(pr.number, body="説明")
    repository.edit_pull_request(pr.number, body="")
    assert body_of(repository, pr.number) == f"Closes #{workspace.number}\n"
    # 新しい本文に書けば、通常の反映と途中の反映を切り替えられる
    assert repository.edit_pull_request(pr.number, body=f"Refs #{workspace.number}").partial
    assert not repository.edit_pull_request(pr.number, body=f"Closes #{workspace.number}\n\n戻す").partial


def test_body_of_branch_pull_request_can_be_cleared(repository):
    repository.create_branch("develop")
    workspace = repository.create_task("t").start(base="develop")
    write(repository.root / "a.txt", "a\n")
    workspace.stage("a.txt")
    workspace.commit("a")
    workspace.submit()
    repository.pull_request().merge()
    pr = repository.branch("develop").submit(into="main")
    repository.edit_pull_request(pr.number, body="説明")
    repository.edit_pull_request(pr.number, body="")
    assert body_of(repository, pr.number) == ""


def test_merge_uses_latest_pull_request(repository):
    """古い PullRequest から merge しても、GitHubの最新の内容（途中の反映に変えた）で後処理する。"""
    workspace, old = submitted(repository)
    assert not old.partial
    repository.edit_pull_request(old.number, body=f"Refs #{workspace.number}")
    result = old.merge()
    assert result.closed_issue is None and result.workspace_rebuilt
    assert repository.task(workspace.number).state == "open"
    assert repository.git.has_remote_branch(workspace.branch)


def test_merge_can_be_resumed_after_partial_failure(repository, monkeypatch):
    """マージの後でIssueを閉じるのに失敗しても、もう一度 merge すれば残りの後処理だけを行う。

    develop へのマージでは、GitHubは本文の Closes でIssueを閉じない（ecowork が閉じる）。
    """
    repository.create_branch("develop")
    workspace, pr = submitted(repository, base="develop")
    github = repository.github
    close_issue = github.close_issue

    def failing(*args, **kwargs):
        raise WorkError(ErrorCode.GITHUB_ERROR, "一時的な失敗")

    monkeypatch.setattr(github, "close_issue", failing)
    with pytest.raises(WorkError) as error:
        pr.merge()
    assert f"task merge {pr.number}" in error.value.hint
    assert github.get_pull_request(repository.root, pr.number).state == "merged"
    assert repository.git.has_remote_branch(workspace.branch)

    monkeypatch.setattr(github, "close_issue", close_issue)
    result = repository.pull_request(pr.number).merge()
    assert (result.resumed, result.closed_issue) == (True, workspace.number)
    assert repository.task(workspace.number).state == "closed"
    repository.git.fetch()
    assert not repository.git.has_remote_branch(workspace.branch)
    # 後処理まで済んだPRは、これまでどおり開いていない扱い
    assert code_of(lambda: repository.pull_request(pr.number).merge()) == ErrorCode.PULL_REQUEST_NOT_OPEN


def test_resumed_partial_merge_does_not_rebuild_twice(repository):
    _, pr = submitted(repository, partial=True)
    assert pr.merge().workspace_rebuilt
    assert code_of(lambda: repository.pull_request(pr.number).merge()) == ErrorCode.PULL_REQUEST_NOT_OPEN


def test_ci_result_rules():
    assert _github.ci_result("completed", "success") == _github.PASSED
    assert _github.ci_result("completed", "skipped") == _github.PASSED
    for conclusion in ("failure", "cancelled", "timed_out", "stale", "action_required", "startup_failure", ""):
        assert _github.ci_result("completed", conclusion) == _github.FAILED, conclusion
    for status in ("queued", "in_progress", "waiting", "pending", ""):
        assert _github.ci_result(status, "") == _github.PENDING, status


def test_stale_check_is_failure_everywhere(repository):
    """結果 stale を、待機・マージ・失敗のログで同じく失敗として扱う。"""
    _, pr = submitted(repository)
    github = repository.github
    github.activity[pr.number] = PullRequestActivity((), (), (Check("build", "completed", "stale"),), "MERGEABLE")
    assert code_of(lambda: repository.pull_request(pr.number).merge()) == ErrorCode.CHECKS_FAILED
    sha = github.get_pull_request(repository.root, pr.number).head_sha
    github.runs = [RunInfo(5, "build", pr.head, "pull_request", "completed", "stale", "u", "t", sha)]
    assert code_of(lambda: repository.ci_wait(pr.number, sleep=lambda _: None)) == ErrorCode.CHECKS_FAILED
    assert repository.ci_failed_log()[0] == 5


def test_dedicated_clone_does_not_use_original_hooks(repository, tmp_path):
    """専用のcloneには、元のcloneに結び付いたフックを渡さない（open で clone 先のものを作る）。"""

    class Recorder(Hooks):
        def __init__(self):
            self.roots = []

        def after_switch(self, repository):
            self.roots.append(repository.root)

    original = Recorder()
    repo = Repository(repository.root, github=repository.github, command="ecobuild", hooks=original)
    task = repo.create_task("並行作業")
    repo.clone_workspace(task.number, tmp_path / "plain")
    assert original.roots == []

    clone_hooks = Recorder()
    other = repo.clone_workspace(task.number, tmp_path / "hooked",
                                 open=lambda root: Repository(root, github=repo.github, hooks=clone_hooks))
    assert original.roots == [] and clone_hooks.roots == [other.root]
