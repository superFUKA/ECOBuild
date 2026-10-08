"""試験用の偽のGitHub。リポジトリは手元のbare、PRのマージは実際にbareへ反映する。"""

from __future__ import annotations

import itertools
import re
import subprocess
from dataclasses import replace
from pathlib import Path

from helpers import git
from ecowork.github import (Comment, IssueInfo, IssueRelations, MilestoneInfo, Review, PullRequestActivity,
                            PullRequestInfo, ReleaseInfo, RepositoryInfo, RunInfo)
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
        self.comments: dict[int, list[Comment]] = {}   # Issueのコメント
        self.reviewers: dict[int, list[str]] = {}       # PRのレビュアー
        self.pr_labels: dict[int, list[str]] = {}
        self.parents: dict[int, int] = {}               # 子 → 親
        self.blockers: dict[int, list[int]] = {}        # Issue → 先に終わるべきIssue
        self.milestones: dict[int, MilestoneInfo] = {}
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
    def create_issue(self, repo, title, body, *, labels=(), assignees=()):
        number = next(self._numbers)
        self.issues[number] = IssueInfo(number, title, f"https://example.invalid/issues/{number}", "open", body,
                                        tuple(labels), tuple(self._user(a) for a in assignees))
        return self.issues[number]

    def _user(self, name):
        return self.owner if name == "@me" else name

    def get_issue(self, repo, number):
        if number not in self.issues:
            raise WorkError(ErrorCode.TASK_NOT_FOUND, f"Issue #{number} が見つかりません。")
        return self.issues[number]

    def list_issues(self, repo, *, closed, label=None, assignee=None, search=None):
        return [i for i in self.issues.values() if (closed or i.state == "open")
                and (label is None or label in i.labels)
                and (assignee is None or self._user(assignee) in i.assignees)
                and (search is None or search in i.title or search in i.body)]

    def edit_issue(self, repo, number, *, title=None, body=None, add_labels=(), remove_labels=(),
                   add_assignees=(), remove_assignees=()):
        issue = self.get_issue(repo, number)
        labels = [l for l in issue.labels if l not in remove_labels] + [l for l in add_labels if l not in issue.labels]
        removed = {self._user(a) for a in remove_assignees}
        assignees = [a for a in issue.assignees if a not in removed]
        assignees += [self._user(a) for a in add_assignees if self._user(a) not in assignees]
        self.issues[number] = replace(issue, title=issue.title if title is None else title,
                                      body=issue.body if body is None else body,
                                      labels=tuple(labels), assignees=tuple(assignees))

    def comment_issue(self, repo, number, body):
        self.get_issue(repo, number)
        self.comments.setdefault(number, []).append(Comment(self.owner, body))

    def issue_comments(self, repo, number):
        self.get_issue(repo, number)
        return list(self.comments.get(number, []))

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

    def delete_secret(self, repo, name):
        if name not in self.secrets:
            raise WorkError(ErrorCode.INVALID_ARGUMENT, f"シークレット {name} はありません。")
        del self.secrets[name]

    def list_secrets(self, repo):
        return sorted(self.secrets)

    def list_releases(self, repo):
        return list(self.releases)

    def close_issue(self, repo, number, *, not_planned=False):
        self.issues[number] = replace(self.issues[number], state="closed")
        if not_planned:
            self.not_planned.add(number)

    # 親子・依存・マイルストーン
    def issue_relation(self, repo, number):
        self.get_issue(repo, number)
        children = [self.issues[c] for c, p in self.parents.items() if p == number]
        return IssueRelations(self.parents.get(number), len(children),
                              sum(1 for c in children if c.state == "closed"),
                              sum(1 for b in self.blockers.get(number, []) if self.issues[b].state == "open"),
                              sum(1 for n, bs in self.blockers.items() if number in bs
                                  and self.issues[n].state == "open"))

    def issue_relations(self, repo, *, closed):
        return {n: self.issue_relation(repo, n) for n, i in self.issues.items() if closed or i.state == "open"}

    def sub_issues(self, repo, number):
        return [self.issues[c] for c, p in sorted(self.parents.items()) if p == number]

    def add_sub_issue(self, repo, parent, child):
        self.get_issue(repo, parent), self.get_issue(repo, child)
        if child in self.parents:  # GitHubも、親のあるIssueは付け替えの指定がなければ断る
            raise WorkError(ErrorCode.GITHUB_ERROR, "GitHubに断られました：Sub issue may only have one parent")
        self.parents[child] = parent

    def remove_sub_issue(self, repo, parent, child):
        if self.parents.get(child) == parent:
            del self.parents[child]

    def blocked_by(self, repo, number):
        return [self.issues[b] for b in self.blockers.get(number, [])]

    def blocking(self, repo, number):
        return [self.issues[n] for n, bs in sorted(self.blockers.items()) if number in bs]

    def add_blocked_by(self, repo, number, blocker):
        self.get_issue(repo, number), self.get_issue(repo, blocker)
        if blocker in self.blockers.get(number, []):
            raise WorkError(ErrorCode.GITHUB_ERROR, "GitHubに断られました：Dependency already exists")
        self.blockers.setdefault(number, []).append(blocker)

    def remove_blocked_by(self, repo, number, blocker):
        if blocker in self.blockers.get(number, []):
            self.blockers[number].remove(blocker)

    def list_milestones(self, repo, *, closed):
        return [m for m in self.milestones.values() if closed or m.state == "open"]

    def create_milestone(self, repo, title, *, due, description):
        number = len(self.milestones) + 1
        self.milestones[number] = MilestoneInfo(number, title, "open", f"https://example.invalid/milestone/{number}",
                                                due, description)
        return self.milestones[number]

    def edit_milestone(self, repo, number, *, title=None, due=None, description=None, state=None):
        m = self.milestones[number]
        self.milestones[number] = replace(m, title=m.title if title is None else title,
                                          due=m.due if due is None else (due or None),
                                          description=m.description if description is None else description,
                                          state=m.state if state is None else state)
        old, new = m.title, self.milestones[number].title
        for n, issue in self.issues.items():
            if issue.milestone == old:
                self.issues[n] = replace(issue, milestone=new)
        return self.milestones[number]

    def set_issue_milestone(self, repo, number, milestone):
        title = None if milestone is None else self.milestones[milestone].title
        self.issues[number] = replace(self.get_issue(repo, number), milestone=title)

    # PR
    def create_pull_request(self, repo, *, head, base, title, body, draft=False):
        number = next(self._numbers)
        sha = git(self.bare, "rev-parse", head)
        self.pulls[number] = PullRequestInfo(number, title, f"https://example.invalid/pull/{number}", "open",
                                             head, base, body, sha, author=self.owner, draft=draft)
        return self._current(self.pulls[number])

    def list_pull_requests(self, repo, *, closed):
        return [self._current(pr) for pr in self.pulls.values() if closed or pr.state == "open"]

    def pull_request_diff(self, repo, number):
        pr = self.get_pull_request(repo, number)
        return git(self.bare, "diff", f"{pr.base}...{pr.head_sha}")

    def _activity(self, number):
        return self.activity.get(number, PullRequestActivity((), (), (), "MERGEABLE"))

    def comment_pull_request(self, repo, number, body):
        self.get_pull_request(repo, number)
        a = self._activity(number)
        self.activity[number] = replace(a, comments=a.comments + (Comment(self.owner, body),))

    def review_pull_request(self, repo, number, *, event, body):
        pr = self.get_pull_request(repo, number)
        if event != "comment" and pr.author == self.owner:
            raise WorkError(ErrorCode.OWN_PULL_REQUEST, f"自分のPR #{number} は承認・修正依頼できません（GitHubの制限）。")
        state = {"approve": "APPROVED", "request_changes": "CHANGES_REQUESTED", "comment": "COMMENTED"}[event]
        a = self._activity(number)
        self.activity[number] = replace(a, reviews=a.reviews + (Review(self.owner, state, body),))

    def edit_pull_request(self, repo, number, *, title=None, body=None, base=None, add_reviewers=(),
                          remove_reviewers=(), add_labels=(), remove_labels=()):
        pr = self.get_pull_request(repo, number)
        self.pulls[number] = replace(self.pulls[number], title=pr.title if title is None else title,
                                     body=pr.body if body is None else body, base=pr.base if base is None else base)
        reviewers = [r for r in self.reviewers.get(number, []) if r not in remove_reviewers]
        self.reviewers[number] = reviewers + [r for r in add_reviewers if r not in reviewers]
        labels = [l for l in self.pr_labels.get(number, []) if l not in remove_labels]
        self.pr_labels[number] = labels + [l for l in add_labels if l not in labels]

    def reopen_pull_request(self, repo, number):
        self.pulls[number] = replace(self.pulls[number], state="open")

    def set_pull_request_draft(self, repo, number, draft):
        self.pulls[number] = replace(self.pulls[number], draft=draft)

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
