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


class GitHub(Protocol):
    def create_repository(self, name: str, *, owner: str | None, private: bool, description: str) -> RepositoryInfo: ...
    def create_issue(self, repo: Path, title: str, body: str) -> IssueInfo: ...
    def get_issue(self, repo: Path, number: int) -> IssueInfo: ...
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
        self._gh(args, cwd=None)
        data = self._json(["repo", "view", full_name, "--json", "nameWithOwner,url"], cwd=None)
        return RepositoryInfo(data["nameWithOwner"], data["url"] + ".git", data["url"])

    def create_issue(self, repo, title, body):
        url = self._gh(["issue", "create", "--title", title, "--body", body], cwd=repo).stdout.strip()
        return self.get_issue(repo, _number_from_url(url))

    def get_issue(self, repo, number):
        completed = self._gh(["issue", "view", str(number), "--json", "number,title,url,state,body"],
                             cwd=repo, check=False)
        if not completed.ok:
            raise WorkError(ErrorCode.TASK_NOT_FOUND, f"Issue #{number} が見つかりません。",
                                details=completed.output)
        data = json.loads(completed.stdout)
        return IssueInfo(data["number"], data["title"], data["url"], data["state"].lower(), data.get("body") or "")

    def close_issue(self, repo, number, *, not_planned=False):
        reason = "not planned" if not_planned else "completed"
        self._gh(["issue", "close", str(number), "--reason", reason], cwd=repo)

    def create_pull_request(self, repo, *, head, base, title, body):
        url = self._gh(["pr", "create", "--head", head, "--base", base, "--title", title, "--body", body],
                       cwd=repo).stdout.strip()
        return self.get_pull_request(repo, _number_from_url(url))

    def get_pull_request(self, repo, number):
        completed = self._gh(["pr", "view", str(number), "--json", _PR_FIELDS], cwd=repo, check=False)
        if not completed.ok:
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
        self._gh(args, cwd=repo)

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
            raise WorkError(
                ErrorCode.GITHUB_ERROR,
                f"gh {' '.join(args[:2])} に失敗しました。",
                hint="gh auth status で認証を確認してください。",
                details=failure.completed.output,
            ) from None


_PR_FIELDS = "number,title,url,state,headRefName,baseRefName,body,headRefOid"


def _pull_request(data: dict) -> PullRequestInfo:
    return PullRequestInfo(
        number=data["number"], title=data["title"], url=data["url"], state=data["state"].lower(),
        head=data["headRefName"], base=data["baseRefName"], body=data.get("body") or "",
        head_sha=data.get("headRefOid"),
    )


def _number_from_url(url: str) -> int:
    match = re.search(r"/(?:issues|pull)/(\d+)\s*$", url)
    if match is None:
        raise WorkError(ErrorCode.GITHUB_ERROR, f"gh の出力からURLを読み取れません：{url!r}")
    return int(match.group(1))


def default() -> GitHub:
    """GitHubへの接続の既定。試験ではこの関数を差し替える。"""
    return GhCli()
