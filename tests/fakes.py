"""試験用の偽のGitHub。リポジトリは手元のbare、PRのマージは実際にbareへ反映する。"""

from __future__ import annotations

import itertools
import re
import subprocess
from dataclasses import replace
from pathlib import Path

from helpers import git
from ecowork.github import IssueInfo, PullRequestInfo, RepositoryInfo
from ecowork.errors import ErrorCode, WorkError


class FakeGitHub:
    def __init__(self, root: Path, owner: str = "tester"):
        self.root = root
        self.owner = owner
        self.root.mkdir(parents=True, exist_ok=True)
        self.issues: dict[int, IssueInfo] = {}
        self.pulls: dict[int, PullRequestInfo] = {}
        self.not_planned: set[int] = set()   # 「対応しない」として閉じたIssue
        self._numbers = itertools.count(1)   # GitHubと同じくIssueとPRで番号を共有する
        self._scratch = itertools.count(1)

    # リポジトリ（このFakeは1つのリポジトリだけを扱う）
    def create_repository(self, name, *, owner, private, description):
        self.bare = self.root / f"{name}.git"
        git(self.root, "init", "--quiet", "--bare", "--initial-branch=main", str(self.bare))
        full = f"{owner or self.owner}/{name}"
        self.private = private
        return RepositoryInfo(full, str(self.bare), f"https://example.invalid/{full}")

    def get_repository(self, name):
        bare = getattr(self, "bare", None)
        if bare is None or name.split("/")[-1] != bare.stem:
            raise WorkError(ErrorCode.REPOSITORY_NOT_FOUND, f"GitHubにリポジトリ {name} が見つかりません。")
        full = name if "/" in name else f"{self.owner}/{name}"
        return RepositoryInfo(full, str(bare), f"https://example.invalid/{full}")

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
            raise WorkError(ErrorCode.TASK_NOT_FOUND, f"Issue #{number} が見つかりません。")
        return self.issues[number]

    def close_issue(self, repo, number, *, not_planned=False):
        self.issues[number] = replace(self.issues[number], state="closed")
        if not_planned:
            self.not_planned.add(number)

    # PR
    def create_pull_request(self, repo, *, head, base, title, body):
        number = next(self._numbers)
        sha = git(self.bare, "rev-parse", head)
        self.pulls[number] = PullRequestInfo(number, title, f"https://example.invalid/pull/{number}", "open",
                                             head, base, body, sha)
        return self.pulls[number]

    def get_pull_request(self, repo, number):
        if number not in self.pulls:
            raise WorkError(ErrorCode.NO_PULL_REQUEST, f"PR #{number} が見つかりません。")
        return self._current(self.pulls[number])

    def pull_requests_for_branch(self, repo, head):
        return [self._current(pr) for pr in self.pulls.values() if pr.head == head]

    def _current(self, pr):
        """開いているPRの先頭は、GitHubと同じくブランチの最新を指す。"""
        if pr.state != "open":
            return pr
        return replace(pr, head_sha=git(self.bare, "rev-parse", pr.head))

    def close_pull_request(self, repo, number):
        self.pulls[number] = replace(self._current(self.pulls[number]), state="closed")

    def merge_pull_request(self, repo, number, *, squash, subject):
        pr = self._current(self.pulls[number])
        # GitHubと同じく、PRの最後のコミットは refs/pull/<番号>/head で取得できる
        git(self.bare, "update-ref", f"refs/pull/{number}/head", pr.head_sha)
        scratch = self.root / f"merge-{next(self._scratch)}"
        git(self.root, "clone", "--quiet", str(self.bare), str(scratch))
        git(scratch, "switch", "--quiet", pr.base)
        message = subject or f"{pr.title} (#{number})"
        try:
            if squash:
                git(scratch, "merge", "--squash", f"origin/{pr.head}")
                git(scratch, "commit", "--quiet", "-m", message)
            else:
                git(scratch, "merge", "--no-ff", "-m", message, f"origin/{pr.head}")
        except subprocess.CalledProcessError:
            # GitHubと同じく、作成元と衝突するPRはマージできない
            raise WorkError(ErrorCode.PULL_REQUEST_CONFLICT, f"PR #{number} は作成元と衝突しています。") from None
        git(scratch, "push", "--quiet", "origin", pr.base)
        self.pulls[number] = replace(pr, state="merged")
        # GitHubと同じく、既定ブランチへのマージなら本文のClosesでIssueを閉じる
        if pr.base == "main":
            for match in re.finditer(r"(?i)\bcloses #(\d+)", pr.body):
                issue = int(match.group(1))
                if issue in self.issues:
                    self.close_issue(repo, issue)
