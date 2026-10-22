import json

import pytest

from ecotask import process as _process
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


def test_get_repository_also_reads_whether_it_is_private(monkeypatch):
    """get_repository の後の is_private は、GitHub に聞き直さない（module show で2回聞いていた）。"""
    recorder = Recorder({"repo view": (0, json.dumps({"nameWithOwner": "o/r", "url": "https://github.com/o/r",
                                                      "isArchived": False, "isPrivate": True}))})
    monkeypatch.setattr(_process, "run", recorder)
    gh = _github.GhCli()
    assert gh.get_repository("o/r").full_name == "o/r"
    assert gh.is_private("o/r") is True
    assert len(recorder.calls) == 1


def test_repository_name_is_remembered_in_the_clone(remote_and_clone, monkeypatch):
    """所有者/名前（gh repo view）は clone の git の設定に覚え、次のコマンドでは聞かない。origin が変われば聞き直す。"""
    _, work = remote_and_clone
    asked = []
    real = _process.run

    def run(args, **kw):
        if args[:3] == ["gh", "repo", "view"]:
            asked.append(args)
            return _process.Completed(tuple(args), 0, json.dumps({"owner": {"login": "o"}, "name": "r"}), "")
        return real(args, **kw)
    monkeypatch.setattr(_process, "run", run)
    assert _github.GhCli().repository_name(work) == "o/r"
    assert _github.GhCli().repository_name(work) == "o/r"
    assert len(asked) == 1
    real(["git", "remote", "set-url", "origin", "https://github.com/o/renamed.git"], cwd=work)
    _github.GhCli().repository_name(work)
    assert len(asked) == 2


def test_remembered_board_is_read_with_the_board_list(remote_and_clone, monkeypatch):
    """前に見つけたボードは、ボードの一覧と同じ問い合わせで定義も読み、get_board で聞き直さない。"""
    _, work = remote_and_clone
    project = {"id": "P", "number": 3, "title": "t", "url": "https://github.com/users/o/projects/3", "closed": False,
               "public": False, "repositories": {"nodes": [{"nameWithOwner": "o/r"}]},
               "fields": {"nodes": [{"id": "F", "name": "Status", "dataType": "SINGLE_SELECT", "options": []}]}}
    queries = []
    real = _process.run

    def run(args, **kw):
        if args[:3] == ["gh", "api", "graphql"]:
            queries.append(json.loads(kw["input"]))
            data = {"repository": {"projectsV2": {"nodes": [
                {"url": project["url"], "shortDescription": "ECOBuild", "closed": False}]}}}
            if "repositoryOwner" in queries[-1]["query"]:
                data["repositoryOwner"] = {"projectV2": project}
            return _process.Completed(tuple(args), 0, json.dumps({"data": data}), "")
        return real(args, **kw)
    monkeypatch.setattr(_process, "run", run)
    first = _github.GhCli("o/r")
    first.repository_boards(work)                 # まだ覚えていない：一覧だけ
    first.get_board(work, "o", 3)
    assert len(queries) == 2
    second = _github.GhCli("o/r")
    second.repository_boards(work)                # 覚えたボードの定義も一緒に読む
    assert second.get_board(work, "o", 3).id == "P"
    assert len(queries) == 3
    assert second.get_board(work, "o", 3).id == "P"   # 2回目（書いた後の読み直し）は聞き直す
    assert len(queries) == 4


def _details_node(**changes):
    ref = lambda n, state="OPEN": {"number": n, "title": f"t{n}", "url": f"u{n}", "state": state}
    node = {"number": 7, "title": "x", "url": "u7", "state": "OPEN", "stateReason": None, "body": "本文",
            "createdAt": "2026-10-01T00:00:00Z", "closedAt": None, "parent": ref(3),
            "subIssuesSummary": {"total": 1, "completed": 0}, "issueDependenciesSummary": {"blockedBy": 1, "blocking": 0},
            "milestone": None, "assignees": {"nodes": [{"login": "me"}]}, "labels": {"nodes": []},
            "projectItems": {"nodes": [{"id": "I1", "project": {"id": "P1"}, "fieldValues": {"nodes": [
                {"name": "In Progress", "field": {"name": "Status"}}]}}]},
            "comments": {"pageInfo": {"hasNextPage": False}, "nodes": [{"author": {"login": "a"}, "body": "c"}]},
            "subIssues": {"pageInfo": {"hasNextPage": False}, "nodes": [ref(8)]},
            "blockedBy": {"pageInfo": {"hasNextPage": False}, "nodes": [ref(5, "CLOSED")]},
            "blocking": {"pageInfo": {"hasNextPage": False}, "nodes": []}}
    return {**node, **changes}


def test_issue_details_reads_everything_in_one_query(monkeypatch, tmp_path):
    """task status の詳細（Issue・ボードの値・コメント・親・子・依存）は GraphQL 1回（以前は gh を7回）。"""
    recorder = Recorder({"api graphql": (0, json.dumps({"data": {"repository": {"issue": _details_node()}}}))})
    monkeypatch.setattr(_process, "run", recorder)
    details = _github.GhCli("o/r").issue_details(tmp_path, 7)
    assert len(recorder.calls) == 1
    assert details.record.issue.body == "本文" and details.record.relations.parent == 3
    assert details.items[0][0] == "P1" and details.items[0][1].values == {"Status": "In Progress"}
    assert details.comments == (_github.Comment("a", "c"),)
    assert (details.parent.number, [i.number for i in details.sub_issues]) == (3, [8])
    assert [(i.number, i.state) for i in details.blocked_by] == [(5, "closed")] and details.blocking == ()


def test_issue_details_reads_the_rest_of_long_lists(monkeypatch, tmp_path):
    """1回で読み切れないコメントだけ読み足す。"""
    node = _details_node(comments={"pageInfo": {"hasNextPage": True}, "nodes": []})
    recorder = Recorder({"api graphql": (0, json.dumps({"data": {"repository": {"issue": node}}})),
                         "issue view": (0, json.dumps({"comments": [{"author": {"login": "b"}, "body": "d"}] * 101}))})
    monkeypatch.setattr(_process, "run", recorder)
    details = _github.GhCli("o/r").issue_details(tmp_path, 7)
    assert len(details.comments) == 101 and len(recorder.calls) == 2


def test_reusing_reads_reads_an_issue_once_until_something_is_written(monkeypatch, tmp_path):
    """1つの操作の中で同じIssueを何度も確かめても、gh は1回（書いた後は読み直す）。"""
    from ecotask import github as _task_github
    issue = json.dumps({"number": 7, "title": "x", "url": "u", "state": "OPEN"})
    recorder = Recorder({"issue view": (0, issue), "issue edit": (0, ""), "pr merge": (0, "")})
    monkeypatch.setattr(_process, "run", recorder)
    github = _github.GhCli("o/r")
    github.get_issue(tmp_path, 7), github.get_issue(tmp_path, 7)
    assert len(recorder.calls) == 2   # 操作の外では今までどおり
    recorder.calls.clear()
    with github.reusing_reads():
        github.get_issue(tmp_path, 7), github.get_issue(tmp_path, 7)
        assert len(recorder.calls) == 1
        github.edit_issue(tmp_path, 7, title="y")
        github.get_issue(tmp_path, 7)
        github.merge_pull_request(tmp_path, 9, squash=True, subject=None)   # GitHub が Issue を閉じるかもしれない
        github.get_issue(tmp_path, 7)
        assert [c[1:3] for c in recorder.calls] == [("issue", "view"), ("issue", "edit"), ("issue", "view"),
                                                    ("pr", "merge"), ("issue", "view")]
        monkeypatch.setattr(_task_github, "REUSE_SECONDS", -1)   # 間が空いた（CI を待った等）
        github.get_issue(tmp_path, 7)
        assert len(recorder.calls) == 6


def test_known_writes_forget_only_what_they_change(monkeypatch, tmp_path):
    """Issue の本文を変えても親子・依存の写しは使い、コメントは写しを捨てない（task start で親と自分の本文に印を書く間）。"""
    issue = json.dumps({"number": 7, "title": "x", "url": "u", "state": "OPEN"})
    relation = json.dumps({"parent": None, "sub": None, "dep": None})
    recorder = Recorder({"issue view": (0, issue), "issue edit": (0, ""), "issue comment": (0, ""),
                         "api repos/{owner}/{repo}/issues/7": (0, relation)})
    monkeypatch.setattr(_process, "run", recorder)
    github = _github.GhCli("o/r")
    with github.reusing_reads():
        github.get_issue(tmp_path, 7), github.issue_relation(tmp_path, 7)
        github.edit_issue(tmp_path, 7, body="印")
        github.comment_issue(tmp_path, 7, "c")
        github.issue_relation(tmp_path, 7), github.get_issue(tmp_path, 7), github.get_issue(tmp_path, 7)
    assert [c[1:3] for c in recorder.calls] == [("issue", "view"), ("api", "repos/{owner}/{repo}/issues/7"),
                                                ("issue", "edit"), ("issue", "comment"), ("issue", "view")]
