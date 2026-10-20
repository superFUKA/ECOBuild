"""GitHub の呼び出し（作業の流れの分：リポジトリ・PR・CI・リリース）。本物は gh を使う。

タスク管理の分（Issue・親子・依存・マイルストーン・ボード）は ecotask.github にあり、ここで広げる。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ecotask import process as _process
from ecotask.github import (Comment, IssueInfo, IssueRelations, MilestoneInfo, TaskGitHub, gh_error, not_found,
                            number_from_url)
from ecotask.github import GhCli as _TaskGhCli
from ecotask.board import description as board_description  # ボードの説明（どのリポジトリのものか。削除の前に書く）

from .errors import ErrorCode, WorkError

# Issue等のデータ（Comment・IssueInfo 等）は ecotask.github のもの。ecowork の公開APIとして、ここからも使う。


@dataclass(frozen=True)
class RepositoryInfo:
    full_name: str        # owner/name
    clone_url: str
    web_url: str
    archived: bool = False   # アーカイブ（読み取り専用）


@dataclass(frozen=True)
class OwnedRepository:
    """所有者（ユーザー・組織）のリポジトリの1件（モジュールの一覧に使う）。"""
    full_name: str              # owner/name
    url: str
    description: str
    private: bool
    archived: bool
    updated: str                # 最後に更新した日時（ISO 8601）
    module_file: str | None     # 既定のブランチの、指定したファイルの中身（ない＝そのファイルがない）


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
    draft: bool = False                 # 下書き（マージできない。task submit で解除）


@dataclass(frozen=True)
class Review:
    author: str
    state: str            # APPROVED / CHANGES_REQUESTED / COMMENTED 等
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


@dataclass(frozen=True)
class Member:
    """リポジトリの共同作業者（invited：招待を送ったが、まだ受けていない）。"""
    login: str
    role: str             # read / triage / write / maintain / admin
    invited: bool = False


@dataclass(frozen=True)
class Protection:
    """ブランチの保護（GitHub の branch protection）。"""
    branch: str
    approvals: int                      # 取り込みに要る承認の数（PR は必須）
    checks: tuple[str, ...] = ()        # 通っている必要がある CI の項目
    enforce_admins: bool = False        # 管理者にも守らせる
    allow_force_pushes: bool = False


@dataclass(frozen=True)
class Access:
    """ログイン中のアカウントと、このリポジトリでの役割（GitHub の権限）。owner_type：持ち主の種類（User・Organization）。"""
    login: str
    role: str             # read / triage / write / maintain / admin
    owner: str = ""
    owner_type: str = ""


# ECOBuild の役割の名前 → GitHub の API の permission
ROLE_PERMISSIONS = {"read": "pull", "triage": "triage", "write": "push", "maintain": "maintain", "admin": "admin"}

_PR_FIELDS = "number,title,url,state,headRefName,baseRefName,body,headRefOid,mergeCommit,author,isDraft"


class GitHub(TaskGitHub, Protocol):
    def create_repository(self, name: str, *, owner: str | None, private: bool, description: str) -> RepositoryInfo: ...
    def get_repository(self, name: str) -> RepositoryInfo: ...
    def is_private(self, name: str) -> bool: ...
    def repository_has_file(self, name: str, path: str) -> bool: ...
    def open_counts(self, name: str) -> tuple[int, int]: ...
    def delete_repository(self, name: str) -> None: ...
    def archive_repository(self, name: str, *, archived: bool = True) -> None: ...
    def owner_repositories(self, owner: str | None, file: str) -> list[OwnedRepository]: ...
    def delete_secret(self, repo: Path, name: str) -> None: ...
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
    def create_pull_request(self, repo: Path, *, head: str, base: str, title: str, body: str,
                            draft: bool = False) -> PullRequestInfo: ...
    def list_pull_requests(self, repo: Path, *, closed: bool,
                           review_requested: str | None = None) -> list[PullRequestInfo]: ...
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
    def access(self, repo: Path) -> Access: ...
    def branch_creators(self, repo: Path) -> dict[str, str]: ...
    def members(self, repo: Path) -> list[Member]: ...
    def add_member(self, repo: Path, login: str, role: str) -> bool: ...
    def remove_member(self, repo: Path, login: str) -> bool: ...
    def branch_protection(self, repo: Path, branch: str) -> Protection | None: ...
    def set_branch_protection(self, repo: Path, protection: Protection) -> None: ...
    def remove_branch_protection(self, repo: Path, branch: str) -> bool: ...
    def check_names(self, repo: Path, ref: str) -> tuple[str, ...]: ...


class GhCli(_TaskGhCli):
    """gh コマンドによる実装（タスク管理の分は ecotask.github.GhCli）。"""

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
            raise gh_error(args, completed)
        data = self._json(["repo", "view", full_name, "--json", "nameWithOwner,url"], cwd=None)
        return RepositoryInfo(data["nameWithOwner"], data["url"] + ".git", data["url"])

    def get_repository(self, name):
        """name は「名前」（ログイン中のユーザーのもの）か「所有者/名前」。"""
        completed = self._gh(["repo", "view", name, "--json", "nameWithOwner,url,isArchived"], cwd=None, check=False)
        if not completed.ok:
            if not not_found(completed):
                raise gh_error(["repo", "view"], completed)
            raise WorkError(ErrorCode.REPOSITORY_NOT_FOUND, f"GitHubにリポジトリ {name} が見つかりません。",
                            details=completed.output)
        data = json.loads(completed.stdout)
        return RepositoryInfo(data["nameWithOwner"], data["url"] + ".git", data["url"], bool(data.get("isArchived")))

    def is_private(self, name):
        return bool(self._json(["repo", "view", name, "--json", "isPrivate"], cwd=None)["isPrivate"])

    def repository_has_file(self, name, path):
        """既定のブランチに path があるか。name は「所有者/名前」。"""
        completed = self._gh(["api", f"repos/{name}/contents/{path}", "--silent"], cwd=None, check=False)
        if not completed.ok and not re.search(r"404|not found", completed.output, re.IGNORECASE):
            raise gh_error(["api", "contents"], completed)
        return completed.ok

    def open_counts(self, name):
        """開いているIssue・PRの数。"""
        owner, _, short = name.partition("/")
        data = self._graphql(None, """query($owner: String!, $name: String!) { repository(owner: $owner, name: $name) {
            issues(states: OPEN) { totalCount } pullRequests(states: OPEN) { totalCount } } }""",
                             owner=owner, name=short)["repository"]
        return data["issues"]["totalCount"], data["pullRequests"]["totalCount"]

    def delete_repository(self, name):
        args = ["repo", "delete", name, "--yes"]
        completed = self._gh(args, cwd=None, check=False)
        if not completed.ok:
            if "delete_repo" in completed.output:
                raise WorkError(ErrorCode.BOARD_PERMISSION,
                                "GitHubへのログインに、リポジトリを削除する権限（delete_repo）がありません。",
                                hint="端末で実行すると、権限の追加を案内します"
                                     "（gh auth refresh -s delete_repo でも追加できます）。",
                                details=completed.output)
            raise gh_error(args, completed)

    def archive_repository(self, name, *, archived=True):
        """アーカイブする（archived=False：元に戻す）。"""
        args = ["repo", "archive" if archived else "unarchive", name, "--yes"]
        completed = self._gh(args, cwd=None, check=False)
        if not completed.ok:
            raise gh_error(args, completed)

    def owner_repositories(self, owner, file):
        """所有者のリポジトリ（owner が None ならログイン中のユーザー）。既定のブランチの file（リポジトリの
        ルートからの相対）の中身も一緒に読む（GraphQL：100件ごとに1回）。共同作業者として入っている他人の
        リポジトリは含めない。"""
        fields = ("repositories(first: 100, after: $after, ownerAffiliations: [OWNER], "
                  "orderBy: {field: UPDATED_AT, direction: DESC}) { pageInfo { hasNextPage endCursor } nodes { "
                  "nameWithOwner url description isPrivate isArchived updatedAt "
                  f'object(expression: "HEAD:{file}") {{ ... on Blob {{ text }} }} }} }}')
        if owner:
            query = ("query($login: String!, $after: String) { owner: repositoryOwner(login: $login) { "
                     "... on User { " + fields + " } ... on Organization { " + fields + " } } }")
        else:
            query = "query($after: String) { owner: viewer { " + fields + " } }"
        result, after = [], None
        while True:
            variables = {"after": after, **({"login": owner} if owner else {})}
            data = self._graphql(None, query, **variables)["owner"]
            if data is None:
                raise WorkError(ErrorCode.REPOSITORY_NOT_FOUND, f"GitHubにユーザー・組織 {owner} が見つかりません。")
            page = data["repositories"]
            result += [OwnedRepository(n["nameWithOwner"], n["url"], n.get("description") or "", bool(n["isPrivate"]),
                                       bool(n["isArchived"]), n["updatedAt"], (n.get("object") or {}).get("text"))
                       for n in page["nodes"]]
            if not page["pageInfo"]["hasNextPage"]:
                return result
            after = page["pageInfo"]["endCursor"]

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
            raise gh_error(["release", "create"], completed)
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
            raise gh_error(["secret", "set"], failure.completed) from None

    def delete_secret(self, repo, name):
        completed = self._gh(["secret", "delete", name], cwd=repo, check=False)
        if not completed.ok:
            if not_found(completed) or "HTTP 404" in completed.output:
                raise WorkError(ErrorCode.INVALID_ARGUMENT, f"シークレット {name} はありません。", details=completed.output)
            raise gh_error(["secret", "delete"], completed)

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
        return self.get_pull_request(repo, number_from_url(url))

    def list_pull_requests(self, repo, *, closed, review_requested=None):
        args = ["pr", "list", "--state", "all" if closed else "open", "--limit", "200", "--json", _PR_FIELDS]
        if review_requested:
            args += ["--search", f"review-requested:{review_requested}"]
        return [_pull_request(item) for item in self._json(args, cwd=repo)]

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
        raise gh_error(args, completed)

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

    def reopen_pull_request(self, repo, number):
        self._gh(["pr", "reopen", str(number)], cwd=repo)

    def set_pull_request_draft(self, repo, number, draft):
        self._gh(["pr", "ready", str(number)] + (["--undo"] if draft else []), cwd=repo)

    def get_pull_request(self, repo, number):
        completed = self._gh(["pr", "view", str(number), "--json", _PR_FIELDS], cwd=repo, check=False)
        if not completed.ok:
            if not not_found(completed):
                raise gh_error(["pr", "view"], completed)
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
        if re.search(r"base branch policy|review(?:s)? required|approving review", completed.output, re.IGNORECASE):
            raise WorkError(ErrorCode.APPROVAL_REQUIRED,
                            f"PR #{number} は、ブランチの保護の条件（承認・CI）を満たしていないため、取り込めません。",
                            details=completed.output)
        raise gh_error(args, completed)

    def close_pull_request(self, repo, number):
        self._gh(["pr", "close", str(number)], cwd=repo)

    def default_branch(self, repo):
        return self._json(["repo", "view", "--json", "defaultBranchRef"], cwd=repo)["defaultBranchRef"]["name"]

    # 役割・共同作業者・ブランチの保護（複数人での開発） ------------------------------------------

    def access(self, repo):
        """ログイン中のアカウントの、このリポジトリでの役割（REST の permissions の一番強いもの）。"""
        data = self._json(["api", "repos/{owner}/{repo}"], cwd=repo)
        granted = data.get("permissions") or {}
        role = next((name for name, key in (("admin", "admin"), ("maintain", "maintain"), ("write", "push"),
                                            ("triage", "triage"), ("read", "pull")) if granted.get(key)), "read")
        owner = data.get("owner") or {}
        return Access(self.current_user(repo), role, owner.get("login", ""), owner.get("type", ""))

    def branch_creators(self, repo):
        """ブランチ → 作った人（リポジトリの活動の記録の branch_creation。新しいものが先なので、作り直したら最後の人）。
        記録が残っていないブランチ（既定のブランチ等）は含まない。"""
        creators: dict[str, str] = {}
        for event in self._paged(repo, "activity?activity_type=branch_creation"):
            name = (event.get("ref") or "").removeprefix("refs/heads/")
            if name and name not in creators and event.get("actor"):
                creators[name] = event["actor"]["login"]
        return creators

    def members(self, repo):
        """共同作業者（招待を受けた人）と、招待中の人。見る権限（管理者）がなければ github_error。"""
        people = [Member(d["login"], d.get("role_name") or "write")
                  for d in self._paged(repo, "collaborators?affiliation=all")]
        people += [Member(d["invitee"]["login"], {"pull": "read", "push": "write"}.get(d.get("permissions"),
                                                                                    d.get("permissions") or "write"), True)
                   for d in self._paged(repo, "invitations") if d.get("invitee")]
        return people

    def add_member(self, repo, login, role):
        """招待を送る（既に共同作業者なら権限を変える）。招待を送ったら True。"""
        result = self._api("PUT", f"collaborators/{login}", {"permission": ROLE_PERMISSIONS[role]}, cwd=repo)
        return bool(result)

    def remove_member(self, repo, login):
        """共同作業者から外す。招待中なら招待を取り消す。外した・取り消したら True。"""
        for invitation in self._paged(repo, "invitations"):
            if (invitation.get("invitee") or {}).get("login", "").casefold() == login.casefold():
                self._api("DELETE", f"invitations/{invitation['id']}", None, cwd=repo)
                return True
        if not any(m.login.casefold() == login.casefold() for m in self.members(repo) if not m.invited):
            return False
        self._api("DELETE", f"collaborators/{login}", None, cwd=repo)
        return True

    def branch_protection(self, repo, branch):
        try:
            data = self._api("GET", f"branches/{branch}/protection", None, cwd=repo)
        except WorkError as error:
            if re.search(r"Branch not protected|HTTP 404", str(error.details or "")):
                return None
            raise _plan_error(error)
        reviews = data.get("required_pull_request_reviews") or {}
        checks = data.get("required_status_checks") or {}
        return Protection(branch, int(reviews.get("required_approving_review_count") or 0),
                          tuple(checks.get("contexts") or ()), bool((data.get("enforce_admins") or {}).get("enabled")),
                          bool((data.get("allow_force_pushes") or {}).get("enabled")))

    def set_branch_protection(self, repo, protection):
        payload = {
            "required_status_checks": {"strict": False, "contexts": list(protection.checks)} if protection.checks
            else None,
            "enforce_admins": protection.enforce_admins,
            "required_pull_request_reviews": {"required_approving_review_count": protection.approvals,
                                              "dismiss_stale_reviews": False},
            "restrictions": None,
            "allow_force_pushes": protection.allow_force_pushes,
            "allow_deletions": False,
        }
        try:
            self._api("PUT", f"branches/{protection.branch}/protection", payload, cwd=repo)
        except WorkError as error:
            raise _plan_error(error)

    def remove_branch_protection(self, repo, branch):
        try:
            self._api("DELETE", f"branches/{branch}/protection", None, cwd=repo)
        except WorkError as error:
            if re.search(r"Branch not protected|HTTP 404", str(error.details or "")):
                return False
            raise _plan_error(error)
        return True

    def check_names(self, repo, ref):
        """そのコミット（ブランチ）の CI の項目の名前（ブランチの保護で必須にする名前）。"""
        data = self._api("GET", f"commits/{ref}/check-runs?per_page=100", None, cwd=repo) or {}
        return tuple(dict.fromkeys(run["name"] for run in data.get("check_runs") or []))

    def _paged(self, repo, path):
        separator = "&" if "?" in path else "?"
        output = self._gh(["api", "--paginate", f"repos/{{owner}}/{{repo}}/{path}{separator}per_page=100",
                           "--jq", ".[]"], cwd=repo).stdout
        return [json.loads(line) for line in output.splitlines() if line.strip()]


def _plan_error(error: WorkError) -> WorkError:
    """料金プランの制限（無料プランの非公開リポジトリではブランチの保護を使えない）なら、そう分かる形にする。"""
    if re.search(r"Upgrade to GitHub Pro|make this repository public", f"{error.message} {error.details or ''}"):
        return WorkError(ErrorCode.PLAN_REQUIRED,
                         "GitHub の無料プランでは、非公開リポジトリにブランチの保護を設定できません。",
                         hint="リポジトリを公開にするか、GitHub Pro・Team（組織）のプランにすると使えます。保護がなくても、"
                              "ECOBuild の [task] require_approval で、ECOBuild を使う人には承認を必須にできます。",
                         details=error.details)
    return error


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


def default() -> GitHub:
    """GitHubへの接続の既定。試験ではこの関数を差し替える。"""
    return GhCli()
