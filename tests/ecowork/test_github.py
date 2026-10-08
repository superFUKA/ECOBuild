import json

import pytest

from ecowork import _process
from ecowork import github as _github
from ecowork.errors import ErrorCode, WorkError


class Recorder:
    """gh の呼び出しを記録し、決まった出力を返す。"""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, args, *, cwd=None, check=True, input=None, env=None):
        self.calls.append(tuple(args))
        key = " ".join(args[1:3])
        returncode, stdout = self.responses[key]
        completed = _process.Completed(tuple(args), returncode, stdout, "" if returncode == 0 else "error")
        if check and returncode != 0:
            raise _process.ProcessFailed(completed)
        return completed


PR = {"number": 9, "title": "t", "url": "https://github.com/o/r/pull/9", "state": "OPEN",
      "headRefName": "task/7", "baseRefName": "main", "body": "Closes #7", "headRefOid": "abc"}


def test_create_issue_reads_number_from_url(monkeypatch, tmp_path):
    recorder = Recorder({
        "issue create": (0, "https://github.com/o/r/issues/7\n"),
        "issue view": (0, json.dumps({"number": 7, "title": "x", "url": "u", "state": "OPEN", "body": None})),
    })
    monkeypatch.setattr(_process, "run", recorder)
    issue = _github.GhCli().create_issue(tmp_path, "x", "")
    assert issue.number == 7 and issue.state == "open" and issue.body == ""
    assert recorder.calls[1][:4] == ("gh", "issue", "view", "7")


def test_pull_request_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(_process, "run", Recorder({
        "pr create": (0, "https://github.com/o/r/pull/9"),
        "pr view": (0, json.dumps(PR)),
    }))
    pr = _github.GhCli().create_pull_request(tmp_path, head="task/7", base="main", title="t", body="Closes #7")
    assert (pr.number, pr.head, pr.base, pr.state, pr.head_sha) == (9, "task/7", "main", "open", "abc")


def test_missing_issue_is_task_not_found(monkeypatch, tmp_path):
    message = "GraphQL: Could not resolve to an issue or pull request with the number of 99."
    monkeypatch.setattr(_process, "run", Recorder({"issue view": (1, message)}))
    with pytest.raises(WorkError) as error:
        _github.GhCli().get_issue(tmp_path, 99)
    assert error.value.code == ErrorCode.TASK_NOT_FOUND


def test_authentication_failure_is_not_task_not_found(monkeypatch, tmp_path):
    """認証の失敗を「Issueがない」と取り違えない（仮運用で見つかった）。"""
    monkeypatch.setattr(_process, "run", Recorder({"issue view": (1, "HTTP 401: Bad credentials")}))
    with pytest.raises(WorkError) as error:
        _github.GhCli().get_issue(tmp_path, 99)
    assert error.value.code == ErrorCode.GITHUB_ERROR and "gh auth status" in error.value.hint


def test_conflicting_merge_is_pull_request_conflict(monkeypatch, tmp_path):
    message = "X Pull request o/r#9 is not mergeable: the merge commit cannot be cleanly created."
    monkeypatch.setattr(_process, "run", Recorder({"pr merge": (1, message)}))
    with pytest.raises(WorkError) as error:
        _github.GhCli().merge_pull_request(tmp_path, 9, squash=True, subject=None)
    assert error.value.code == ErrorCode.PULL_REQUEST_CONFLICT


def test_gh_failure_is_github_error(monkeypatch, tmp_path):
    monkeypatch.setattr(_process, "run", Recorder({"issue close": (1, "")}))
    with pytest.raises(WorkError) as error:
        _github.GhCli().close_issue(tmp_path, 1)
    assert error.value.code == ErrorCode.GITHUB_ERROR


def test_labels_are_created_before_use(monkeypatch, tmp_path):
    recorder = Recorder({
        "label list": (0, json.dumps([{"name": "bug"}])),
        "label create": (0, ""),
        "issue create": (0, "https://github.com/o/r/issues/7\n"),
        "issue view": (0, json.dumps({"number": 7, "title": "x", "url": "u", "state": "OPEN", "body": "",
                                      "labels": [{"name": "bug"}, {"name": "docs"}],
                                      "assignees": [{"login": "me"}]})),
    })
    monkeypatch.setattr(_process, "run", recorder)
    issue = _github.GhCli().create_issue(tmp_path, "x", "", labels=("bug", "docs"), assignees=("@me",))
    assert issue.labels == ("bug", "docs") and issue.assignees == ("me",)
    assert ("gh", "label", "create", "docs") in recorder.calls
    assert not any(call[:4] == ("gh", "label", "create", "bug") for call in recorder.calls)
    create = next(call for call in recorder.calls if call[1:3] == ("issue", "create"))
    assert create[-6:] == ("--label", "bug", "--label", "docs", "--assignee", "@me")


def test_issue_filters_and_edits_become_gh_options(monkeypatch, tmp_path):
    recorder = Recorder({"issue list": (0, "[]"), "issue edit": (0, ""), "issue comment": (0, ""),
                         "label list": (0, "[]"), "label create": (0, "")})
    monkeypatch.setattr(_process, "run", recorder)
    gh = _github.GhCli()
    gh.list_issues(tmp_path, closed=False, label="bug", assignee="@me", search="crash")
    assert recorder.calls[0][-6:] == ("--label", "bug", "--assignee", "@me", "--search", "crash")
    gh.edit_issue(tmp_path, 3, add_labels=("x",), remove_assignees=("@me",))
    assert recorder.calls[-1] == ("gh", "issue", "edit", "3", "--add-label", "x", "--remove-assignee", "@me")
    gh.comment_issue(tmp_path, 3, "メモ")
    assert recorder.calls[-1] == ("gh", "issue", "comment", "3", "--body", "メモ")


def test_missing_secret_is_invalid_argument(monkeypatch, tmp_path):
    """本物のGitHubは、ないシークレットの削除に HTTP 404 を返す（仮運用4回目で見つかった）。"""
    message = "failed to delete secret X: HTTP 404 (https://api.github.com/repos/o/r/actions/secrets/X)"
    monkeypatch.setattr(_process, "run", Recorder({"secret delete": (1, message)}))
    with pytest.raises(WorkError) as error:
        _github.GhCli().delete_secret(tmp_path, "X")
    assert error.value.code == ErrorCode.INVALID_ARGUMENT


def test_status_contexts_are_normalized(monkeypatch, tmp_path):
    """コミットの状態（state）も Check Run と同じ形にする（失敗を「実行中」と取り違えない）。"""
    rollup = [{"name": "build", "status": "COMPLETED", "conclusion": "SUCCESS"},
              {"context": "ci/legacy", "state": "FAILURE"}, {"context": "ci/slow", "state": "PENDING"}]
    monkeypatch.setattr(_process, "run", Recorder({"pr view": (0, json.dumps(
        {"reviews": [], "comments": [], "statusCheckRollup": rollup, "mergeable": "MERGEABLE"}))}))
    checks = _github.GhCli().pull_request_activity(tmp_path, 9).checks
    assert [(c.name, _github.ci_result(c.status, c.conclusion)) for c in checks] == [
        ("build", _github.PASSED), ("ci/legacy", _github.FAILED), ("ci/slow", _github.PENDING)]


def test_edit_pull_request_uses_rest_api(monkeypatch, tmp_path):
    """gh pr edit は使わない（gh 2.65 で Projects (classic) のエラーになる。仮運用5回目）。本文の空も送る。"""
    calls = []

    def run(args, *, cwd=None, check=True, input=None, env=None):
        calls.append((tuple(args), None if input is None else json.loads(input)))
        stdout = json.dumps([{"name": "old"}, {"name": "keep"}]) if args[-1].endswith("/labels") else ""
        return _process.Completed(tuple(args), 0, stdout, "")

    monkeypatch.setattr(_process, "run", run)
    monkeypatch.setattr(_github.GhCli, "_ensure_labels", lambda self, repo, labels: None)
    _github.GhCli().edit_pull_request(tmp_path, 9, body="", base="develop", add_labels=("new",),
                                      remove_labels=("old",))
    assert all("edit" not in args for args, _ in calls)
    assert calls[0] == (("gh", "api", "--method", "PATCH", "repos/{owner}/{repo}/pulls/9", "--input", "-"),
                        {"body": "", "base": "develop"})
    assert calls[-1][1] == {"labels": ["keep", "new"]}
