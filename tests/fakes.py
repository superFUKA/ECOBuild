"""試験用の偽のGitHub。リポジトリは手元のbare、PRのマージは実際にbareへ反映する。"""

from __future__ import annotations

import itertools
import re
from dataclasses import replace
from pathlib import Path

from helpers import git
from ecobuild._github import IssueInfo, PullRequestInfo, RepositoryInfo
from ecobuild.errors import EcoBuildError, ErrorCode


class FakeGitHub:
    def __init__(self, root: Path, owner: str = "tester"):
        self.root = root
        self.owner = owner
        self.root.mkdir(parents=True, exist_ok=True)
        self.issues: dict[int, IssueInfo] = {}
        self.pulls: dict[int, PullRequestInfo] = {}
        self._numbers = itertools.count(1)   # GitHubと同じくIssueとPRで番号を共有する
        self._scratch = itertools.count(1)

    # リポジトリ（このFakeは1つのリポジトリだけを扱う）
    def create_repository(self, name, *, owner, private, description):
        self.bare = self.root / f"{name}.git"
        git(self.root, "init", "--quiet", "--bare", "--initial-branch=main", str(self.bare))
        full = f"{owner or self.owner}/{name}"
        self.private = private
        return RepositoryInfo(full, str(self.bare), f"https://example.invalid/{full}")

    def use_bare(self, bare: Path) -> None:
        self.bare = bare

    def default_branch(self, repo):
        return "main"

    # Issue
    def create_issue(self, repo, title, body):
        number = next(self._numbers)
        self.issues[number] = IssueInfo(number, title, f"https://example.invalid/issues/{number}", "open", body)
        return self.issues[number]

    def get_issue(self, repo, number):
        if number not in self.issues:
            raise EcoBuildError(ErrorCode.TASK_NOT_FOUND, f"Issue #{number} が見つかりません。")
        return self.issues[number]

    def close_issue(self, repo, number):
        self.issues[number] = replace(self.issues[number], state="closed")

    # PR
    def create_pull_request(self, repo, *, head, base, title, body):
        number = next(self._numbers)
        sha = git(self.bare, "rev-parse", head)
        self.pulls[number] = PullRequestInfo(number, title, f"https://example.invalid/pull/{number}", "open",
                                             head, base, body, sha)
        return self.pulls[number]

    def get_pull_request(self, repo, number):
        if number not in self.pulls:
            raise EcoBuildError(ErrorCode.NO_PULL_REQUEST, f"PR #{number} が見つかりません。")
        return self._current(self.pulls[number])

    def pull_requests_for_branch(self, repo, head):
        return [self._current(pr) for pr in self.pulls.values() if pr.head == head]

    def _current(self, pr):
        """開いているPRの先頭は、GitHubと同じくブランチの最新を指す。"""
        if pr.state != "open":
            return pr
        return replace(pr, head_sha=git(self.bare, "rev-parse", pr.head))

    def merge_pull_request(self, repo, number, *, squash, subject):
        pr = self._current(self.pulls[number])
        scratch = self.root / f"merge-{next(self._scratch)}"
        git(self.root, "clone", "--quiet", str(self.bare), str(scratch))
        git(scratch, "switch", "--quiet", pr.base)
        message = subject or f"{pr.title} (#{number})"
        if squash:
            git(scratch, "merge", "--squash", f"origin/{pr.head}")
            git(scratch, "commit", "--quiet", "-m", message)
        else:
            git(scratch, "merge", "--no-ff", "-m", message, f"origin/{pr.head}")
        git(scratch, "push", "--quiet", "origin", pr.base)
        self.pulls[number] = replace(pr, state="merged")
        # GitHubと同じく、既定ブランチへのマージなら本文のClosesでIssueを閉じる
        if pr.base == "main":
            for match in re.finditer(r"(?i)\bcloses #(\d+)", pr.body):
                issue = int(match.group(1))
                if issue in self.issues:
                    self.close_issue(repo, issue)
