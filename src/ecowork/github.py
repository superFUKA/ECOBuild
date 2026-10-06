"""GitHub の呼び出し。本物は gh を使う。試験では同じメソッドを持つ偽物に差し替える。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from . import _process
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


@dataclass(frozen=True)
class PullRequestActivity:
    """PRのレビュー・コメント・CIの結果（I-035）。"""
    reviews: tuple[Review, ...]
    comments: tuple[Comment, ...]
    checks: tuple[Check, ...]
    mergeable: str        # MERGEABLE / CONFLICTING / UNKNOWN


@dataclass(frozen=True)
class ReleaseInfo:
    tag: str
    name: str
    url: str
    latest: bool = False


class GitHub(Protocol):
    def create_repository(self, name: str, *, owner: str | None, private: bool, description: str) -> RepositoryInfo: ...
    def get_repository(self, name: str) -> RepositoryInfo: ...
    def create_issue(self, repo: Path, title: str, body: str) -> IssueInfo: ...
    def get_issue(self, repo: Path, number: int) -> IssueInfo: ...
    def list_issues(self, repo: Path, *, closed: bool) -> list[IssueInfo]: ...
    def edit_issue(self, repo: Path, number: int, *, title: str | None, body: str | None) -> None: ...
    def reopen_issue(self, repo: Path, number: int) -> None: ...
    def pull_request_activity(self, repo: Path, number: int) -> PullRequestActivity: ...
    def merged_pull_requests(self, repo: Path) -> list[PullRequestInfo]: ...
    def create_release(self, repo: Path, *, tag: str, title: str, notes: str, target: str) -> ReleaseInfo: ...
    def list_releases(self, repo: Path) -> list[ReleaseInfo]: ...
    def close_issue(self, repo: Path, number: int, *, not_planned: bool = False) -> None: ...
    def create_pull_request(self, repo: Path, *, head: str, base: str, title: str, body: str) -> PullRequestInfo: ...
    def get_pull_request(self, repo: Path, number: int) -> PullRequestInfo: ...
    def pull_requests_for_branch(self, repo: Path, head: str) -> list[PullRequestInfo]: ...
    def merge_pull_request(self, repo: Path, number: int, *, squash: bool, subject: str | None) -> None: ...
    def close_pull_request(self, repo: Path, number: int) -> None: ...
    def default_branch(self, repo: Path) -> str: ...


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

    def create_issue(self, repo, title, body):
        url = self._gh(["issue", "create", "--title", title, "--body", body], cwd=repo).stdout.strip()
        return self.get_issue(repo, _number_from_url(url))

    def get_issue(self, repo, number):
        completed = self._gh(["issue", "view", str(number), "--json", "number,title,url,state,body"],
                             cwd=repo, check=False)
        if not completed.ok:
            if not _not_found(completed):
                raise _gh_error(["issue", "view"], completed)
            raise WorkError(ErrorCode.TASK_NOT_FOUND, f"Issue #{number} が見つかりません。",
                                details=completed.output)
        data = json.loads(completed.stdout)
        return IssueInfo(data["number"], data["title"], data["url"], data["state"].lower(), data.get("body") or "")

    def close_issue(self, repo, number, *, not_planned=False):
        reason = "not planned" if not_planned else "completed"
        self._gh(["issue", "close", str(number), "--reason", reason], cwd=repo)

    def list_issues(self, repo, *, closed):
        args = ["issue", "list", "--state", "all" if closed else "open", "--limit", "200",
                "--json", "number,title,url,state,body"]
        return [IssueInfo(d["number"], d["title"], d["url"], d["state"].lower(), d.get("body") or "")
                for d in self._json(args, cwd=repo)]

    def edit_issue(self, repo, number, *, title, body):
        args = ["issue", "edit", str(number)]
        if title is not None:
            args += ["--title", title]
        if body is not None:
            args += ["--body", body]
        self._gh(args, cwd=repo)

    def reopen_issue(self, repo, number):
        self._gh(["issue", "reopen", str(number)], cwd=repo)

    def pull_request_activity(self, repo, number):
        data = self._json(["pr", "view", str(number), "--json", "reviews,comments,statusCheckRollup,mergeable"],
                          cwd=repo)
        reviews = tuple(Review((r.get("author") or {}).get("login", ""), r.get("state", ""), r.get("body") or "")
                        for r in data.get("reviews") or [])
        comments = tuple(Comment((c.get("author") or {}).get("login", ""), c.get("body") or "")
                         for c in data.get("comments") or [])
        checks = tuple(Check(c.get("name") or c.get("context") or "", (c.get("status") or c.get("state") or "").lower(),
                             (c.get("conclusion") or "").lower())
                       for c in data.get("statusCheckRollup") or [])
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

    def list_releases(self, repo):
        data = self._json(["release", "list", "--limit", "100", "--json", "tagName,name,isLatest"], cwd=repo)
        url = self._json(["repo", "view", "--json", "url"], cwd=repo)["url"]
        return [ReleaseInfo(d["tagName"], d.get("name") or d["tagName"], f"{url}/releases/tag/{d['tagName']}",
                            bool(d.get("isLatest"))) for d in data]

    def create_pull_request(self, repo, *, head, base, title, body):
        url = self._gh(["pr", "create", "--head", head, "--base", base, "--title", title, "--body", body],
                       cwd=repo).stdout.strip()
        return self.get_pull_request(repo, _number_from_url(url))

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


_PR_FIELDS = "number,title,url,state,headRefName,baseRefName,body,headRefOid,mergeCommit"


def _pull_request(data: dict) -> PullRequestInfo:
    return PullRequestInfo(
        number=data["number"], title=data["title"], url=data["url"], state=data["state"].lower(),
        head=data["headRefName"], base=data["baseRefName"], body=data.get("body") or "",
        head_sha=data.get("headRefOid"),
        merge_commit=(data.get("mergeCommit") or {}).get("oid"),
    )


def _number_from_url(url: str) -> int:
    match = re.search(r"/(?:issues|pull)/(\d+)\s*$", url)
    if match is None:
        raise WorkError(ErrorCode.GITHUB_ERROR, f"gh の出力からURLを読み取れません：{url!r}")
    return int(match.group(1))


def default() -> GitHub:
    """GitHubへの接続の既定。試験ではこの関数を差し替える。"""
    return GhCli()
