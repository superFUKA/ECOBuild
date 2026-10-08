"""GitHub の呼び出し。本物は gh を使う。試験では同じメソッドを持つ偽物に差し替える。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from . import _process
from . import board as _board
from .errors import ErrorCode, WorkError


@dataclass(frozen=True)
class RepositoryInfo:
    full_name: str        # owner/name
    clone_url: str
    web_url: str


@dataclass(frozen=True)
class IssueInfo:
    number: int
    title: str
    url: str
    state: str            # open / closed
    body: str = ""
    labels: tuple[str, ...] = ()
    assignees: tuple[str, ...] = ()     # ログイン名
    milestone: str | None = None        # マイルストーンの題名


@dataclass(frozen=True)
class IssueRelations:
    """Issueの親子・依存の要約（一覧1回で取れる分）。"""
    parent: int | None = None           # 親のIssue
    sub_total: int = 0                  # 子のIssueの数
    sub_completed: int = 0              # そのうち閉じたもの
    blocked_by: int = 0                 # 先に終わるべきIssueのうち、開いているものの数
    blocking: int = 0                   # このIssueを待っているIssueのうち、開いているものの数


@dataclass(frozen=True)
class MilestoneInfo:
    number: int
    title: str
    state: str            # open / closed
    url: str
    due: str | None = None              # 期日（YYYY-MM-DD）
    description: str = ""
    open_issues: int = 0
    closed_issues: int = 0


@dataclass(frozen=True)
class PullRequestInfo:
    number: int
    title: str
    url: str
    state: str            # open / closed / merged
    head: str
    base: str
    body: str = ""
    head_sha: str | None = None
    merge_commit: str | None = None     # マージ済みなら、作成元に入ったコミット
    author: str = ""
    draft: bool = False                 # 下書き（マージできない。pr ready で解除）


@dataclass(frozen=True)
class Review:
    author: str
    state: str            # APPROVED / CHANGES_REQUESTED / COMMENTED 等
    body: str


@dataclass(frozen=True)
class Comment:
    author: str
    body: str


@dataclass(frozen=True)
class Check:
    name: str
    status: str           # completed / in_progress / queued 等
    conclusion: str       # success / failure 等（終わっていなければ空）


PASSED, FAILED, PENDING = "passed", "failed", "pending"
_PASSED_CONCLUSIONS = ("success", "skipped", "neutral")


def ci_result(status: str, conclusion: str) -> str:
    """CIの結果（Check・RunInfo の status と conclusion）を、通った・失敗・終わっていない に分ける。

    待機（ci wait）・マージの判定・失敗のログの案内で同じ規則を使う。終わっているのに success・skipped・
    neutral でないもの（failure・cancelled・timed_out・stale・action_required・未知の値・結果なし）は失敗とする。
    """
    if status != "completed" and not conclusion:
        return PENDING
    return PASSED if conclusion in _PASSED_CONCLUSIONS else FAILED


@dataclass(frozen=True)
class PullRequestActivity:
    """PRのレビュー・コメント・CIの結果（I-035）。"""
    reviews: tuple[Review, ...]
    comments: tuple[Comment, ...]
    checks: tuple[Check, ...]
    mergeable: str        # MERGEABLE / CONFLICTING / UNKNOWN


@dataclass(frozen=True)
class RunInfo:
    """CI（GitHub Actions）の1回の実行。"""
    id: int
    workflow: str
    branch: str
    event: str            # push / pull_request / workflow_dispatch 等
    status: str           # queued / in_progress / completed
    conclusion: str       # success / failure 等（終わっていなければ空）
    url: str
    created: str
    head_sha: str = ""    # 実行したコミット


@dataclass(frozen=True)
class ReleaseInfo:
    tag: str
    name: str
    url: str
    latest: bool = False


class GitHub(Protocol):
    def create_repository(self, name: str, *, owner: str | None, private: bool, description: str) -> RepositoryInfo: ...
    def get_repository(self, name: str) -> RepositoryInfo: ...
    def is_private(self, name: str) -> bool: ...
    def create_issue(self, repo: Path, title: str, body: str, *, labels: tuple[str, ...] = (),
                     assignees: tuple[str, ...] = ()) -> IssueInfo: ...
    def get_issue(self, repo: Path, number: int) -> IssueInfo: ...
    def list_issues(self, repo: Path, *, closed: bool, label: str | None = None, assignee: str | None = None,
                    search: str | None = None) -> list[IssueInfo]: ...
    def edit_issue(self, repo: Path, number: int, *, title: str | None = None, body: str | None = None,
                   add_labels: tuple[str, ...] = (), remove_labels: tuple[str, ...] = (),
                   add_assignees: tuple[str, ...] = (), remove_assignees: tuple[str, ...] = ()) -> None: ...
    def comment_issue(self, repo: Path, number: int, body: str) -> None: ...
    def issue_comments(self, repo: Path, number: int) -> list[Comment]: ...
    def delete_secret(self, repo: Path, name: str) -> None: ...
    def reopen_issue(self, repo: Path, number: int) -> None: ...
    def pull_request_activity(self, repo: Path, number: int) -> PullRequestActivity: ...
    def merged_pull_requests(self, repo: Path) -> list[PullRequestInfo]: ...
    def create_release(self, repo: Path, *, tag: str, title: str, notes: str, target: str) -> ReleaseInfo: ...
    def list_releases(self, repo: Path) -> list[ReleaseInfo]: ...
    def list_runs(self, repo: Path, *, branch: str | None, limit: int) -> list[RunInfo]: ...
    def failed_log(self, repo: Path, run_id: int) -> str: ...
    def rerun(self, repo: Path, run_id: int, *, failed_only: bool) -> None: ...
    def dispatch(self, repo: Path, workflow: str, *, ref: str) -> None: ...
    def set_secret(self, repo: Path, name: str, value: str) -> None: ...
    def list_secrets(self, repo: Path) -> list[str]: ...
    def close_issue(self, repo: Path, number: int, *, not_planned: bool = False) -> None: ...
    def create_pull_request(self, repo: Path, *, head: str, base: str, title: str, body: str,
                            draft: bool = False) -> PullRequestInfo: ...
    def list_pull_requests(self, repo: Path, *, closed: bool) -> list[PullRequestInfo]: ...
    def pull_request_diff(self, repo: Path, number: int) -> str: ...
    def comment_pull_request(self, repo: Path, number: int, body: str) -> None: ...
    def review_pull_request(self, repo: Path, number: int, *, event: str, body: str) -> None: ...
    def edit_pull_request(self, repo: Path, number: int, *, title: str | None = None, body: str | None = None,
                          base: str | None = None, add_reviewers: tuple[str, ...] = (),
                          remove_reviewers: tuple[str, ...] = (), add_labels: tuple[str, ...] = (),
                          remove_labels: tuple[str, ...] = ()) -> None: ...
    def reopen_pull_request(self, repo: Path, number: int) -> None: ...
    def set_pull_request_draft(self, repo: Path, number: int, draft: bool) -> None: ...
    def get_pull_request(self, repo: Path, number: int) -> PullRequestInfo: ...
    def pull_requests_for_branch(self, repo: Path, head: str) -> list[PullRequestInfo]: ...
    def merge_pull_request(self, repo: Path, number: int, *, squash: bool, subject: str | None) -> None: ...
    def close_pull_request(self, repo: Path, number: int) -> None: ...
    def default_branch(self, repo: Path) -> str: ...
    # 親子（Sub-issues）・依存（Issue dependencies）・マイルストーン
    def issue_relations(self, repo: Path, *, closed: bool) -> dict[int, IssueRelations]: ...
    def issue_relation(self, repo: Path, number: int) -> IssueRelations: ...
    def sub_issues(self, repo: Path, number: int) -> list[IssueInfo]: ...
    def add_sub_issue(self, repo: Path, parent: int, child: int) -> None: ...
    def remove_sub_issue(self, repo: Path, parent: int, child: int) -> None: ...
    def blocked_by(self, repo: Path, number: int) -> list[IssueInfo]: ...
    def blocking(self, repo: Path, number: int) -> list[IssueInfo]: ...
    def add_blocked_by(self, repo: Path, number: int, blocker: int) -> None: ...
    def remove_blocked_by(self, repo: Path, number: int, blocker: int) -> None: ...
    def list_milestones(self, repo: Path, *, closed: bool) -> list[MilestoneInfo]: ...
    def create_milestone(self, repo: Path, title: str, *, due: str | None, description: str) -> MilestoneInfo: ...
    def edit_milestone(self, repo: Path, number: int, *, title: str | None = None, due: str | None = None,
                       description: str | None = None, state: str | None = None) -> MilestoneInfo: ...
    def set_issue_milestone(self, repo: Path, number: int, milestone: int | None) -> None: ...
    # ボード（GitHub Projects。ghのトークンに project の権限が必要）
    def list_boards(self, repo: Path, owner: str | None) -> list[_board.BoardInfo]: ...
    def get_board(self, repo: Path, owner: str, number: int) -> _board.BoardInfo: ...
    def link_board(self, repo: Path, board_id: str, *, link: bool) -> None: ...
    def board_items(self, repo: Path, board_id: str, *, closed: bool) -> dict[int, _board.BoardItem]: ...
    def board_item(self, repo: Path, number: int, board_id: str) -> _board.BoardItem | None: ...
    def add_board_item(self, repo: Path, number: int, board_id: str) -> _board.BoardItem: ...
    def set_board_value(self, repo: Path, board_id: str, item_id: str, field: _board.BoardField, value: str) -> None: ...
    def clear_board_value(self, repo: Path, board_id: str, item_id: str, field_id: str) -> None: ...


class GhCli:
    """gh コマンドによる実装。repoは手元のcloneのパス（originからリポジトリを決める）。"""

    def create_repository(self, name, *, owner, private, description):
        full_name = name if owner is None else f"{owner}/{name}"
        args = ["repo", "create", full_name, "--private" if private else "--public"]
        if description:
            args += ["--description", description]
        completed = self._gh(args, cwd=None, check=False)
        if not completed.ok:
            if "already exists" in completed.output:
                raise WorkError(ErrorCode.ALREADY_EXISTS, f"GitHubにリポジトリ {full_name} が既にあります。",
                                hint="別の名前にしてください。", details=completed.output)
            raise _gh_error(args, completed)
        data = self._json(["repo", "view", full_name, "--json", "nameWithOwner,url"], cwd=None)
        return RepositoryInfo(data["nameWithOwner"], data["url"] + ".git", data["url"])

    def get_repository(self, name):
        """name は「名前」（ログイン中のユーザーのもの）か「所有者/名前」。"""
        completed = self._gh(["repo", "view", name, "--json", "nameWithOwner,url"], cwd=None, check=False)
        if not completed.ok:
            if not _not_found(completed):
                raise _gh_error(["repo", "view"], completed)
            raise WorkError(ErrorCode.REPOSITORY_NOT_FOUND, f"GitHubにリポジトリ {name} が見つかりません。",
                            details=completed.output)
        data = json.loads(completed.stdout)
        return RepositoryInfo(data["nameWithOwner"], data["url"] + ".git", data["url"])

    def is_private(self, name):
        return bool(self._json(["repo", "view", name, "--json", "isPrivate"], cwd=None)["isPrivate"])

    def create_issue(self, repo, title, body, *, labels=(), assignees=()):
        self._ensure_labels(repo, labels)
        args = ["issue", "create", "--title", title, "--body", body]
        for label in labels:
            args += ["--label", label]
        for assignee in assignees:
            args += ["--assignee", assignee]
        url = self._gh(args, cwd=repo).stdout.strip()
        return self.get_issue(repo, _number_from_url(url))

    def get_issue(self, repo, number):
        completed = self._gh(["issue", "view", str(number), "--json", _ISSUE_FIELDS],
                             cwd=repo, check=False)
        if not completed.ok:
            if not _not_found(completed):
                raise _gh_error(["issue", "view"], completed)
            raise WorkError(ErrorCode.TASK_NOT_FOUND, f"Issue #{number} が見つかりません。",
                                details=completed.output)
        return _issue(json.loads(completed.stdout))

    def close_issue(self, repo, number, *, not_planned=False):
        reason = "not planned" if not_planned else "completed"
        self._gh(["issue", "close", str(number), "--reason", reason], cwd=repo)

    def list_issues(self, repo, *, closed, label=None, assignee=None, search=None):
        args = ["issue", "list", "--state", "all" if closed else "open", "--limit", "200", "--json", _ISSUE_FIELDS]
        for option, value in (("--label", label), ("--assignee", assignee), ("--search", search)):
            if value:
                args += [option, value]
        return [_issue(d) for d in self._json(args, cwd=repo)]

    def edit_issue(self, repo, number, *, title=None, body=None, add_labels=(), remove_labels=(),
                   add_assignees=(), remove_assignees=()):
        self._ensure_labels(repo, add_labels)
        args = ["issue", "edit", str(number)]
        if title is not None:
            args += ["--title", title]
        if body is not None:
            args += ["--body", body]
        for option, values in (("--add-label", add_labels), ("--remove-label", remove_labels),
                               ("--add-assignee", add_assignees), ("--remove-assignee", remove_assignees)):
            for value in values:
                args += [option, value]
        self._gh(args, cwd=repo)

    def comment_issue(self, repo, number, body):
        self._gh(["issue", "comment", str(number), "--body", body], cwd=repo)

    def issue_comments(self, repo, number):
        data = self._json(["issue", "view", str(number), "--json", "comments"], cwd=repo)
        return [Comment((c.get("author") or {}).get("login", ""), c.get("body") or "") for c in data.get("comments") or []]

    def _ensure_labels(self, repo, labels):
        """ラベルはリポジトリにないと付けられないため、なければ作る。"""
        if not labels:
            return
        existing = {d["name"] for d in self._json(["label", "list", "--limit", "500", "--json", "name"], cwd=repo)}
        for label in labels:
            if label not in existing:
                self._gh(["label", "create", label], cwd=repo)

    def reopen_issue(self, repo, number):
        self._gh(["issue", "reopen", str(number)], cwd=repo)

    def pull_request_activity(self, repo, number):
        data = self._json(["pr", "view", str(number), "--json", "reviews,comments,statusCheckRollup,mergeable"],
                          cwd=repo)
        reviews = tuple(Review((r.get("author") or {}).get("login", ""), r.get("state", ""), r.get("body") or "")
                        for r in data.get("reviews") or [])
        comments = tuple(Comment((c.get("author") or {}).get("login", ""), c.get("body") or "")
                         for c in data.get("comments") or [])
        checks = tuple(_check(c) for c in data.get("statusCheckRollup") or [])
        return PullRequestActivity(reviews, comments, checks, data.get("mergeable") or "UNKNOWN")

    def merged_pull_requests(self, repo):
        data = self._json(["pr", "list", "--state", "merged", "--limit", "200", "--json", _PR_FIELDS], cwd=repo)
        return [_pull_request(item) for item in data]

    def create_release(self, repo, *, tag, title, notes, target):
        completed = self._gh(["release", "create", tag, "--title", title or tag, "--notes", notes,
                              "--target", target], cwd=repo, check=False)
        if not completed.ok:
            if "already exists" in completed.output:
                raise WorkError(ErrorCode.ALREADY_EXISTS, f"リリース（タグ）{tag} は既にあります。",
                                details=completed.output)
            raise _gh_error(["release", "create"], completed)
        return next(r for r in self.list_releases(repo) if r.tag == tag)

    def list_runs(self, repo, *, branch, limit):
        args = ["run", "list", "--limit", str(limit),
                "--json", "databaseId,workflowName,headBranch,event,status,conclusion,url,createdAt,headSha"]
        if branch:
            args += ["--branch", branch]
        return [RunInfo(d["databaseId"], d.get("workflowName") or "", d.get("headBranch") or "", d.get("event") or "",
                        (d.get("status") or "").lower(), (d.get("conclusion") or "").lower(), d.get("url") or "",
                        d.get("createdAt") or "", d.get("headSha") or "") for d in self._json(args, cwd=repo)]

    def failed_log(self, repo, run_id):
        return self._gh(["run", "view", str(run_id), "--log-failed"], cwd=repo).stdout

    def rerun(self, repo, run_id, *, failed_only):
        self._gh(["run", "rerun", str(run_id)] + (["--failed"] if failed_only else []), cwd=repo)

    def dispatch(self, repo, workflow, *, ref):
        self._gh(["workflow", "run", workflow, "--ref", ref], cwd=repo)

    def set_secret(self, repo, name, value):
        # 値は標準入力で渡す（コマンドの引数に残さない）
        try:
            _process.run(["gh", "secret", "set", name], cwd=repo, input=value, env={"GH_PROMPT_DISABLED": "1"})
        except _process.ProcessFailed as failure:
            raise _gh_error(["secret", "set"], failure.completed) from None

    def delete_secret(self, repo, name):
        completed = self._gh(["secret", "delete", name], cwd=repo, check=False)
        if not completed.ok:
            if _not_found(completed) or "HTTP 404" in completed.output:
                raise WorkError(ErrorCode.INVALID_ARGUMENT, f"シークレット {name} はありません。", details=completed.output)
            raise _gh_error(["secret", "delete"], completed)

    def list_secrets(self, repo):
        return [d["name"] for d in self._json(["secret", "list", "--json", "name"], cwd=repo)]

    def list_releases(self, repo):
        data = self._json(["release", "list", "--limit", "100", "--json", "tagName,name,isLatest"], cwd=repo)
        url = self._json(["repo", "view", "--json", "url"], cwd=repo)["url"]
        return [ReleaseInfo(d["tagName"], d.get("name") or d["tagName"], f"{url}/releases/tag/{d['tagName']}",
                            bool(d.get("isLatest"))) for d in data]

    def create_pull_request(self, repo, *, head, base, title, body, draft=False):
        args = ["pr", "create", "--head", head, "--base", base, "--title", title, "--body", body]
        url = self._gh(args + (["--draft"] if draft else []), cwd=repo).stdout.strip()
        return self.get_pull_request(repo, _number_from_url(url))

    def list_pull_requests(self, repo, *, closed):
        data = self._json(["pr", "list", "--state", "all" if closed else "open", "--limit", "200",
                           "--json", _PR_FIELDS], cwd=repo)
        return [_pull_request(item) for item in data]

    def pull_request_diff(self, repo, number):
        return self._gh(["pr", "diff", str(number)], cwd=repo).stdout

    def comment_pull_request(self, repo, number, body):
        self._gh(["pr", "comment", str(number), "--body", body], cwd=repo)

    def review_pull_request(self, repo, number, *, event, body):
        flag = {"approve": "--approve", "request_changes": "--request-changes", "comment": "--comment"}[event]
        args = ["pr", "review", str(number), flag] + (["--body", body] if body else [])
        completed = self._gh(args, cwd=repo, check=False)
        if completed.ok:
            return
        if re.search(r"your own pull request", completed.output, re.IGNORECASE):
            raise WorkError(ErrorCode.OWN_PULL_REQUEST, f"自分のPR #{number} は承認・修正依頼できません（GitHubの制限）。",
                            hint="コメントとして返すなら --comment を使ってください。", details=completed.output)
        raise _gh_error(args, completed)

    def edit_pull_request(self, repo, number, *, title=None, body=None, base=None, add_reviewers=(),
                          remove_reviewers=(), add_labels=(), remove_labels=()):
        # gh pr edit は使わない：gh 2.65 等では、廃止された Projects (classic) を問い合わせて失敗する（仮運用で確認）。
        # REST API で直接変える。
        fields = {key: value for key, value in (("title", title), ("body", body), ("base", base)) if value is not None}
        if fields:
            self._api("PATCH", f"pulls/{number}", fields, cwd=repo)
        if add_reviewers:
            self._api("POST", f"pulls/{number}/requested_reviewers", {"reviewers": list(add_reviewers)}, cwd=repo)
        if remove_reviewers:
            self._api("DELETE", f"pulls/{number}/requested_reviewers", {"reviewers": list(remove_reviewers)},
                      cwd=repo)
        if add_labels or remove_labels:
            self._ensure_labels(repo, add_labels)
            current = [d["name"] for d in self._json(["api", f"repos/{{owner}}/{{repo}}/issues/{number}/labels"],
                                                     cwd=repo)]
            labels = [name for name in current if name not in remove_labels]
            self._api("PUT", f"issues/{number}/labels",
                      {"labels": labels + [name for name in add_labels if name not in labels]}, cwd=repo)

    def _api(self, method, path, payload, *, cwd):
        """REST API（repos/<所有者>/<名前>/<path>）を呼ぶ。payload はJSONで標準入力から渡す。"""
        args = ["api", "--method", method, f"repos/{{owner}}/{{repo}}/{path}"]
        if payload is not None:
            args += ["--input", "-"]
        try:
            completed = _process.run(["gh", *args], cwd=cwd, input=None if payload is None else json.dumps(payload),
                                     env={"GH_PROMPT_DISABLED": "1"})
        except _process.ProcessFailed as failure:
            raise _api_error(failure.completed) from None
        return json.loads(completed.stdout) if completed.stdout.strip() else None

    def reopen_pull_request(self, repo, number):
        self._gh(["pr", "reopen", str(number)], cwd=repo)

    def set_pull_request_draft(self, repo, number, draft):
        self._gh(["pr", "ready", str(number)] + (["--undo"] if draft else []), cwd=repo)

    def get_pull_request(self, repo, number):
        completed = self._gh(["pr", "view", str(number), "--json", _PR_FIELDS], cwd=repo, check=False)
        if not completed.ok:
            if not _not_found(completed):
                raise _gh_error(["pr", "view"], completed)
            raise WorkError(ErrorCode.NO_PULL_REQUEST, f"PR #{number} が見つかりません。",
                                details=completed.output)
        return _pull_request(json.loads(completed.stdout))

    def pull_requests_for_branch(self, repo, head):
        data = self._json(["pr", "list", "--head", head, "--state", "all", "--json", _PR_FIELDS], cwd=repo)
        return [_pull_request(item) for item in data]

    def merge_pull_request(self, repo, number, *, squash, subject):
        args = ["pr", "merge", str(number), "--squash" if squash else "--merge"]
        if subject:
            args += ["--subject", subject]
        completed = self._gh(args, cwd=repo, check=False)
        if completed.ok:
            return
        if re.search(r"merge conflict|not mergeable", completed.output, re.IGNORECASE):
            raise WorkError(ErrorCode.PULL_REQUEST_CONFLICT,
                            f"PR #{number} は作成元と衝突しているため、マージできません。", details=completed.output)
        raise _gh_error(args, completed)

    def close_pull_request(self, repo, number):
        self._gh(["pr", "close", str(number)], cwd=repo)

    def default_branch(self, repo):
        return self._json(["repo", "view", "--json", "defaultBranchRef"], cwd=repo)["defaultBranchRef"]["name"]

    # 親子・依存・マイルストーン（REST。gh に専用のコマンドがない） -----------------------------

    def issue_relations(self, repo, *, closed):
        query = (".[] | select(.pull_request == null) | {number, parent: .parent_issue_url, "
                 "sub: .sub_issues_summary, dep: .issue_dependencies_summary}")
        state = "all" if closed else "open"
        output = self._gh(["api", "--paginate", f"repos/{{owner}}/{{repo}}/issues?state={state}&per_page=100",
                           "--jq", query], cwd=repo).stdout
        result = {}
        for line in output.splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            sub, dep = d.get("sub") or {}, d.get("dep") or {}
            result[d["number"]] = IssueRelations(
                _number_from_url(d["parent"]) if d.get("parent") else None, sub.get("total", 0),
                sub.get("completed", 0), dep.get("blocked_by", 0), dep.get("blocking", 0))
        return result

    def issue_relation(self, repo, number):
        d = self._json(["api", f"repos/{{owner}}/{{repo}}/issues/{number}", "--jq",
                        "{parent: .parent_issue_url, sub: .sub_issues_summary, dep: .issue_dependencies_summary}"],
                       cwd=repo)
        sub, dep = d.get("sub") or {}, d.get("dep") or {}
        return IssueRelations(_number_from_url(d["parent"]) if d.get("parent") else None, sub.get("total", 0),
                              sub.get("completed", 0), dep.get("blocked_by", 0), dep.get("blocking", 0))

    def sub_issues(self, repo, number):
        return self._rest_issues(repo, f"issues/{number}/sub_issues")

    def add_sub_issue(self, repo, parent, child):
        self._api("POST", f"issues/{parent}/sub_issues", {"sub_issue_id": self._issue_id(repo, child)}, cwd=repo)

    def remove_sub_issue(self, repo, parent, child):
        self._api("DELETE", f"issues/{parent}/sub_issue", {"sub_issue_id": self._issue_id(repo, child)}, cwd=repo)

    def blocked_by(self, repo, number):
        return self._rest_issues(repo, f"issues/{number}/dependencies/blocked_by")

    def blocking(self, repo, number):
        return self._rest_issues(repo, f"issues/{number}/dependencies/blocking")

    def add_blocked_by(self, repo, number, blocker):
        self._api("POST", f"issues/{number}/dependencies/blocked_by", {"issue_id": self._issue_id(repo, blocker)},
                  cwd=repo)

    def remove_blocked_by(self, repo, number, blocker):
        self._api("DELETE", f"issues/{number}/dependencies/blocked_by/{self._issue_id(repo, blocker)}", None, cwd=repo)

    def list_milestones(self, repo, *, closed):
        state = "all" if closed else "open"
        output = self._gh(["api", "--paginate", f"repos/{{owner}}/{{repo}}/milestones?state={state}&per_page=100"
                           "&sort=due_on", "--jq", ".[]"], cwd=repo).stdout
        return [_milestone(json.loads(line)) for line in output.splitlines() if line.strip()]

    def create_milestone(self, repo, title, *, due, description):
        payload = {"title": title, "description": description}
        if due:
            payload["due_on"] = _due_on(due)
        return _milestone(self._api("POST", "milestones", payload, cwd=repo))

    def edit_milestone(self, repo, number, *, title=None, due=None, description=None, state=None):
        payload = {key: value for key, value in (("title", title), ("description", description), ("state", state))
                   if value is not None}
        if due is not None:
            payload["due_on"] = _due_on(due) if due else None
        return _milestone(self._api("PATCH", f"milestones/{number}", payload, cwd=repo))

    def set_issue_milestone(self, repo, number, milestone):
        self._api("PATCH", f"issues/{number}", {"milestone": milestone}, cwd=repo)

    # ボード（GraphQL。gh project は使わない：gh の版で壊れやすいため） ----------------------------

    def list_boards(self, repo, owner):
        owner = owner or self._repo_name(repo)[0]
        data = self._graphql(repo, """
            query($login: String!) { repositoryOwner(login: $login) { ... on ProjectV2Owner {
              projectsV2(first: 100) { nodes { id number title url closed } } } } }""", login=owner)
        owner_data = data.get("repositoryOwner")
        if owner_data is None:
            raise WorkError(ErrorCode.REPOSITORY_NOT_FOUND, f"GitHubに所有者 {owner} が見つかりません。")
        return [_board.BoardInfo(n["id"], n["number"], n["title"], n["url"], (), n["closed"])
                for n in owner_data["projectsV2"]["nodes"]]

    def get_board(self, repo, owner, number):
        data = self._graphql(repo, """
            query($login: String!, $number: Int!) { repositoryOwner(login: $login) { ... on ProjectV2Owner {
              projectV2(number: $number) { id number title url closed fields(first: 100) { nodes {
                ... on ProjectV2Field { id name dataType }
                ... on ProjectV2SingleSelectField { id name dataType options { id name } }
                ... on ProjectV2IterationField { id name dataType
                    configuration { iterations { id title } completedIterations { id title } } } } } } } } }""",
                             login=owner, number=number)
        project = (data.get("repositoryOwner") or {}).get("projectV2")
        if project is None:
            raise WorkError(ErrorCode.NO_BOARD, f"ボード {owner} の {number} 番が見つかりません。",
                            hint="URLと、そのボードを見られるアカウントか確かめてください。")
        fields = []
        for node in project["fields"]["nodes"]:
            if not node:
                continue
            options = [_board.BoardOption(o["id"], o["name"]) for o in node.get("options") or []]
            configuration = node.get("configuration") or {}
            options += [_board.BoardOption(i["id"], i["title"])
                        for i in (configuration.get("iterations") or []) + (configuration.get("completedIterations") or [])]
            fields.append(_board.BoardField(node["id"], node["name"], node["dataType"], tuple(options)))
        return _board.BoardInfo(project["id"], project["number"], project["title"], project["url"], tuple(fields),
                                project["closed"])

    def link_board(self, repo, board_id, *, link):
        repository_id = self._graphql(repo, """
            query($owner: String!, $name: String!) { repository(owner: $owner, name: $name) { id } }""",
                                      **self._repo_vars(repo))["repository"]["id"]
        mutation = "linkProjectV2ToRepository" if link else "unlinkProjectV2FromRepository"
        self._graphql(repo, f"""
            mutation($project: ID!, $repository: ID!) {{
              {mutation}(input: {{projectId: $project, repositoryId: $repository}}) {{ repository {{ id }} }} }}""",
                      project=board_id, repository=repository_id)

    def board_items(self, repo, board_id, *, closed):
        result, after = {}, None
        while True:
            data = self._graphql(repo, """
                query($owner: String!, $name: String!, $states: [IssueState!], $after: String) {
                  repository(owner: $owner, name: $name) { issues(first: 50, after: $after, states: $states) {
                    pageInfo { hasNextPage endCursor }
                    nodes { number projectItems(first: 20) { nodes { id project { id } """ + _VALUES + """ } } } } } }""",
                                 states=None if closed else ["OPEN"], after=after, **self._repo_vars(repo))
            issues = data["repository"]["issues"]
            for node in issues["nodes"]:
                item = _board_item(node["projectItems"]["nodes"], board_id)
                if item is not None:
                    result[node["number"]] = item
            if not issues["pageInfo"]["hasNextPage"]:
                return result
            after = issues["pageInfo"]["endCursor"]

    def board_item(self, repo, number, board_id):
        return _board_item(self._issue_items(repo, number)["projectItems"]["nodes"], board_id)

    def add_board_item(self, repo, number, board_id):
        issue = self._issue_items(repo, number)
        item = _board_item(issue["projectItems"]["nodes"], board_id)
        if item is not None:
            return item
        data = self._graphql(repo, """
            mutation($project: ID!, $content: ID!) {
              addProjectV2ItemById(input: {projectId: $project, contentId: $content}) { item { id } } }""",
                             project=board_id, content=issue["id"])
        return _board.BoardItem(data["addProjectV2ItemById"]["item"]["id"], {})

    def set_board_value(self, repo, board_id, item_id, field, value):
        self._graphql(repo, """
            mutation($project: ID!, $item: ID!, $field: ID!, $value: ProjectV2FieldValue!) {
              updateProjectV2ItemFieldValue(input: {projectId: $project, itemId: $item, fieldId: $field,
                                                    value: $value}) { projectV2Item { id } } }""",
                      project=board_id, item=item_id, field=field.id, value=_field_value(field, value))

    def clear_board_value(self, repo, board_id, item_id, field_id):
        self._graphql(repo, """
            mutation($project: ID!, $item: ID!, $field: ID!) {
              clearProjectV2ItemFieldValue(input: {projectId: $project, itemId: $item, fieldId: $field}) {
                projectV2Item { id } } }""", project=board_id, item=item_id, field=field_id)

    def _issue_items(self, repo, number):
        data = self._graphql(repo, """
            query($owner: String!, $name: String!, $number: Int!) { repository(owner: $owner, name: $name) {
              issue(number: $number) { id projectItems(first: 20) { nodes { id project { id } """ + _VALUES + """ } } } } }""",
                             number=number, **self._repo_vars(repo))
        issue = data["repository"]["issue"]
        if issue is None:
            raise WorkError(ErrorCode.TASK_NOT_FOUND, f"Issue #{number} が見つかりません。")
        return issue

    def _repo_name(self, repo):
        names = self.__dict__.setdefault("_names", {})
        if repo not in names:
            data = self._json(["repo", "view", "--json", "owner,name"], cwd=repo)
            names[repo] = (data["owner"]["login"], data["name"])
        return names[repo]

    def _repo_vars(self, repo):
        owner, name = self._repo_name(repo)
        return {"owner": owner, "name": name}

    def _graphql(self, repo, query, **variables):
        """GraphQL を呼ぶ（本文はJSONで標準入力から渡す）。権限が足りなければ board_permission。"""
        args = ["api", "graphql", "--input", "-"]
        completed = _process.run(["gh", *args], cwd=repo, check=False,
                                 input=json.dumps({"query": query, "variables": variables}),
                                 env={"GH_PROMPT_DISABLED": "1"})
        if "INSUFFICIENT_SCOPES" in completed.output or "required scopes" in completed.output:
            raise WorkError(ErrorCode.BOARD_PERMISSION, "ghのトークンに、ボード（GitHub Projects）を使う権限がありません。",
                            hint="gh auth refresh -s project を実行してください（ブラウザで承認します）。",
                            details=completed.output)
        if not completed.ok:
            match = re.search(r'"message"\s*:\s*"([^"]+)"', completed.output)
            if match and not re.search(r"HTTP 401|Bad credentials", completed.output):
                raise WorkError(ErrorCode.GITHUB_ERROR, f"GitHubに断られました：{match.group(1)}",
                                details=completed.output)
            raise _gh_error(args, completed)
        return json.loads(completed.stdout)["data"]

    def _issue_id(self, repo, number):
        """親子・依存のAPIが使う、Issueの内部のID（番号ではない）。"""
        completed = self._gh(["api", f"repos/{{owner}}/{{repo}}/issues/{number}", "--jq", ".id"], cwd=repo,
                             check=False)
        if not completed.ok:
            if _not_found(completed):
                raise WorkError(ErrorCode.TASK_NOT_FOUND, f"Issue #{number} が見つかりません。", details=completed.output)
            raise _gh_error(["api", "issues"], completed)
        return int(completed.stdout.strip())

    def _rest_issues(self, repo, path):
        output = self._gh(["api", "--paginate", f"repos/{{owner}}/{{repo}}/{path}?per_page=100", "--jq", ".[]"],
                          cwd=repo).stdout
        return [_rest_issue(json.loads(line)) for line in output.splitlines() if line.strip()]

    def _json(self, args, *, cwd):
        return json.loads(self._gh(args, cwd=cwd).stdout)

    def _gh(self, args, *, cwd, check=True):
        try:
            return _process.run(["gh", *args], cwd=cwd, check=check, env={"GH_PROMPT_DISABLED": "1"})
        except _process.ProcessFailed as failure:
            raise _gh_error(args, failure.completed) from None


def _not_found(completed: _process.Completed) -> bool:
    return re.search(r"could not resolve|not found|no pull requests? found", completed.output, re.IGNORECASE) is not None


def _gh_error(args, completed: _process.Completed) -> WorkError:
    authentication = re.search(r"auth|401|credentials", completed.output, re.IGNORECASE)
    return WorkError(
        ErrorCode.GITHUB_ERROR,
        f"gh {' '.join(args[:2])} に失敗しました。",
        hint="gh auth status で認証を確認してください。" if authentication else None,
        details=completed.output,
    )


_PR_FIELDS = "number,title,url,state,headRefName,baseRefName,body,headRefOid,mergeCommit,author,isDraft"
_ISSUE_FIELDS = "number,title,url,state,body,labels,assignees,milestone"


def _issue(data: dict) -> IssueInfo:
    return IssueInfo(data["number"], data["title"], data["url"], data["state"].lower(), data.get("body") or "",
                     tuple(label["name"] for label in data.get("labels") or []),
                     tuple(user["login"] for user in data.get("assignees") or []),
                     (data.get("milestone") or {}).get("title"))


def _rest_issue(data: dict) -> IssueInfo:
    """REST API の形のIssue（gh issue view とは項目の名前が違う）。"""
    return IssueInfo(data["number"], data["title"], data.get("html_url") or "", data["state"], data.get("body") or "",
                     tuple(label["name"] for label in data.get("labels") or []),
                     tuple(user["login"] for user in data.get("assignees") or []),
                     (data.get("milestone") or {}).get("title"))


_FIELD_NAME = "field { ... on ProjectV2FieldCommon { name } }"
_VALUES = ("fieldValues(first: 50) { nodes { "
           f"... on ProjectV2ItemFieldTextValue {{ text {_FIELD_NAME} }} "
           f"... on ProjectV2ItemFieldNumberValue {{ number {_FIELD_NAME} }} "
           f"... on ProjectV2ItemFieldDateValue {{ date {_FIELD_NAME} }} "
           f"... on ProjectV2ItemFieldSingleSelectValue {{ name {_FIELD_NAME} }} "
           f"... on ProjectV2ItemFieldIterationValue {{ title {_FIELD_NAME} }} "
           "} }")


def _board_item(nodes: list, board_id: str) -> _board.BoardItem | None:
    """Issueのボードの項目のうち、そのボードのもの。値はフィールドの名前 → 表示の値（題名は除く）。"""
    for node in nodes:
        if node and node["project"]["id"] == board_id:
            values = {}
            for value in node["fieldValues"]["nodes"]:
                if not value or not value.get("field"):
                    continue
                name = value["field"]["name"]
                if name == "Title":
                    continue
                for key in ("name", "title", "text", "date", "number"):
                    if value.get(key) is not None:
                        shown = value[key]
                        if key == "number" and float(shown).is_integer():
                            shown = int(shown)
                        values[name] = str(shown)
                        break
            return _board.BoardItem(node["id"], values)
    return None


def _field_value(field: _board.BoardField, value: str) -> dict:
    """フィールドの型に合わせた値（ProjectV2FieldValue）。型に合わなければ invalid_argument。"""
    if field.type == "SINGLE_SELECT":
        return {"singleSelectOptionId": _board.find_option(field, value).id}
    if field.type == "ITERATION":
        return {"iterationId": _board.find_option(field, value).id}
    if field.type == "TEXT":
        return {"text": value}
    if field.type == "NUMBER":
        try:
            return {"number": float(value)}
        except ValueError:
            raise WorkError(ErrorCode.INVALID_ARGUMENT, f"{field.name} は数値です：{value}") from None
    if field.type == "DATE":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise WorkError(ErrorCode.INVALID_ARGUMENT, f"{field.name} は日付（YYYY-MM-DD）です：{value}")
        return {"date": value}
    raise WorkError(ErrorCode.INVALID_ARGUMENT, f"{field.name}（{field.type}）は設定できません。",
                    hint="担当者・ラベル・マイルストーン等は ecobuild task edit で変えてください。")


def _milestone(data: dict) -> MilestoneInfo:
    return MilestoneInfo(data["number"], data["title"], data["state"], data.get("html_url") or "",
                         (data.get("due_on") or "")[:10] or None, data.get("description") or "",
                         data.get("open_issues", 0), data.get("closed_issues", 0))


def _due_on(date: str) -> str:
    """期日（YYYY-MM-DD）を、APIの日時の形にする。"""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise WorkError(ErrorCode.INVALID_ARGUMENT, f"期日 {date} は YYYY-MM-DD の形で指定してください。")
    return f"{date}T23:59:59Z"


def _api_error(completed: _process.Completed) -> WorkError:
    """REST API の失敗。GitHubが返した理由（message）を見せる（親子・依存の循環・重複等）。"""
    match = re.search(r'"message"\s*:\s*"([^"]+)"', completed.output)
    if match and not re.search(r"HTTP 401|Bad credentials", completed.output):
        return WorkError(ErrorCode.GITHUB_ERROR, f"GitHubに断られました：{match.group(1)}", details=completed.output)
    return _gh_error(["api"], completed)


def _check(data: dict) -> Check:
    """statusCheckRollup の1件。Check Run（status・conclusion）とコミットの状態（state）を同じ形にそろえる。"""
    name = data.get("name") or data.get("context") or ""
    if "status" not in data and "state" in data:
        state = (data.get("state") or "").lower()          # SUCCESS / FAILURE / ERROR / PENDING / EXPECTED
        if state in ("pending", "expected", ""):
            return Check(name, "pending", "")
        return Check(name, "completed", state)
    return Check(name, (data.get("status") or "").lower(), (data.get("conclusion") or "").lower())


def _pull_request(data: dict) -> PullRequestInfo:
    return PullRequestInfo(
        number=data["number"], title=data["title"], url=data["url"], state=data["state"].lower(),
        head=data["headRefName"], base=data["baseRefName"], body=data.get("body") or "",
        head_sha=data.get("headRefOid"),
        merge_commit=(data.get("mergeCommit") or {}).get("oid"),
        author=(data.get("author") or {}).get("login", ""), draft=bool(data.get("isDraft")),
    )


def _number_from_url(url: str) -> int:
    match = re.search(r"/(?:issues|pull)/(\d+)\s*$", url)
    if match is None:
        raise WorkError(ErrorCode.GITHUB_ERROR, f"gh の出力からURLを読み取れません：{url!r}")
    return int(match.group(1))


def default() -> GitHub:
    """GitHubへの接続の既定。試験ではこの関数を差し替える。"""
    return GhCli()
