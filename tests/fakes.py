"""試験用の偽のGitHub。リポジトリは手元のbare、PRのマージは実際にbareへ反映する。"""

from __future__ import annotations

import itertools
import re
import subprocess
from dataclasses import replace
from pathlib import Path

from helpers import git
from ecowork.github import IssueInfo, PullRequestActivity, PullRequestInfo, ReleaseInfo, RepositoryInfo, RunInfo
from ecowork.errors import ErrorCode, WorkError


class FakeGitHub:
    def __init__(self, root: Path, owner: str = "tester"):
        self.root = root
        self.owner = owner
        self.root.mkdir(parents=True, exist_ok=True)
        self.issues: dict[int, IssueInfo] = {}
        self.pulls: dict[int, PullRequestInfo] = {}
        self.not_planned: set[int] = set()   # 「対応しない」として閉じたIssue
        self.others: dict[str, Path] = {}    # 名前 → 別のリポジトリ（bare）
        self.activity: dict[int, PullRequestActivity] = {}
        self.releases: list[ReleaseInfo] = []
        self.runs: list[RunInfo] = []          # 新しい順
        self.reruns: list[tuple[int, bool]] = []
        self.dispatched: list[tuple[str, str]] = []
        self.secrets: dict[str, str] = {}
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
        short = name.split("/")[-1]
        if short in self.others:  # 試験で登録した別のリポジトリ（link の相手等）
            full = name if "/" in name else f"{self.owner}/{short}"
            return RepositoryInfo(full, "file:///" + self.others[short].as_posix(), f"https://example.invalid/{full}")
        bare = getattr(self, "bare", None)
        if bare is None or name.split("/")[-1] != bare.stem:
            raise WorkError(ErrorCode.REPOSITORY_NOT_FOUND, f"GitHubにリポジトリ {name} が見つかりません。")
        full = name if "/" in name else f"{self.owner}/{name}"
        return RepositoryInfo(full, str(bare), f"https://example.invalid/{full}")

    def is_private(self, name):
        return self.private if getattr(self, "bare", None) is not None and name.endswith(self.bare.stem) else True

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

    def list_issues(self, repo, *, closed):
        return [i for i in self.issues.values() if closed or i.state == "open"]

    def edit_issue(self, repo, number, *, title, body):
        issue = self.get_issue(repo, number)
        self.issues[number] = replace(issue, title=issue.title if title is None else title,
                                      body=issue.body if body is None else body)

    def reopen_issue(self, repo, number):
        self.issues[number] = replace(self.get_issue(repo, number), state="open")
        self.not_planned.discard(number)

    def pull_request_activity(self, repo, number):
        return self.activity.get(number, PullRequestActivity((), (), (), "MERGEABLE"))

    def merged_pull_requests(self, repo):
        return [pr for pr in self.pulls.values() if pr.state == "merged"]

    def create_release(self, repo, *, tag, title, notes, target):
        if any(r.tag == tag for r in self.releases):
            raise WorkError(ErrorCode.ALREADY_EXISTS, f"リリース（タグ）{tag} は既にあります。")
        git(self.bare, "tag", tag, target)
        self.releases = [replace(r, latest=False) for r in self.releases]
        self.releases.insert(0, ReleaseInfo(tag, title or tag, f"https://example.invalid/releases/tag/{tag}", True))
        return self.releases[0]

    def list_runs(self, repo, *, branch, limit):
        return [r for r in self.runs if branch is None or r.branch == branch][:limit]

    def failed_log(self, repo, run_id):
        return f"run {run_id}: error"

    def rerun(self, repo, run_id, *, failed_only):
        self.reruns.append((run_id, failed_only))

    def dispatch(self, repo, workflow, *, ref):
        self.dispatched.append((workflow, ref))

    def set_secret(self, repo, name, value):
        self.secrets[name] = value

    def list_secrets(self, repo):
        return sorted(self.secrets)

    def list_releases(self, repo):
        return list(self.releases)

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
        return self._current(self.pulls[number])

    def get_pull_request(self, repo, number):
        if number not in self.pulls:
            raise WorkError(ErrorCode.NO_PULL_REQUEST, f"PR #{number} が見つかりません。")
        return self._current(self.pulls[number])

    def pull_requests_for_branch(self, repo, head):
        return [self._current(pr) for pr in self.pulls.values() if pr.head == head]

    def _current(self, pr):
        """開いているPRの先頭は、GitHubと同じくブランチの最新を指す（refs/pull/<番号>/head も）。"""
        if pr.state != "open":
            return pr
        sha = git(self.bare, "rev-parse", pr.head)
        git(self.bare, "update-ref", f"refs/pull/{pr.number}/head", sha)
        return replace(pr, head_sha=sha)

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
        self.pulls[number] = replace(pr, state="merged", merge_commit=git(scratch, "rev-parse", "HEAD"))
        # GitHubと同じく、既定ブランチへのマージなら本文のClosesでIssueを閉じる
        if pr.base == "main":
            for match in re.finditer(r"(?i)\bcloses #(\d+)", pr.body):
                issue = int(match.group(1))
                if issue in self.issues:
                    self.close_issue(repo, issue)
