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
