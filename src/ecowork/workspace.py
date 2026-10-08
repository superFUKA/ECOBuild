"""タスク（GitHub Issue）、作業空間、ブランチ、PRと、操作の結果。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from . import github as _github
from .errors import ErrorCode, WorkError

if TYPE_CHECKING:
    from .repository import Repository

WORKSPACE_PREFIX = "task/"
_WORKSPACE = re.compile(r"task/(\d+)")


def workspace_branch(number: int) -> str:
    return f"{WORKSPACE_PREFIX}{number}"


def is_workspace_branch(name: str) -> bool:
    return name.startswith(WORKSPACE_PREFIX)


def workspace_number(name: str) -> int | None:
    match = _WORKSPACE.fullmatch(name)
    return None if match is None else int(match.group(1))


def base_key(branch: str) -> str:
    """作業空間の作成元を記録するgitの設定のキー（手元の写し。本体はIssueの本文の印）。"""
    return f"branch.{branch}.ecowork-base"


# 作業空間の本体はGitHubにあり、手元はその写し（消しても task start で作り直せる）。
# 作成元もGitHubに残すため、Issueの本文の末尾に印（表示されないHTMLのコメント）を書く。
_BASE_MARK = re.compile(r"\s*<!-- ecowork-base: (\S+) -->\s*$")


def issue_base(body: str) -> str | None:
    match = _BASE_MARK.search(body or "")
    return None if match is None else match.group(1)


def without_base(body: str) -> str:
    return _BASE_MARK.sub("", body or "")


def with_base(body: str, base: str) -> str:
    text = without_base(body)
    return (text + "\n\n" if text else "") + f"<!-- ecowork-base: {base} -->"


# 作業空間のPRとIssueのつながり：本文の行 Closes #<番号>（マージでIssueを閉じる）か Refs #<番号>（途中の反映）。
# 本文の作成・書き換え・途中の反映かの判定は、すべてこの関数で行う。
_LINK = re.compile(r"(?im)^(closes|refs) #(\d+)\s*$")


def task_link(body: str, task: int) -> str | None:
    """本文にある、そのIssueとのつながり（"closes"／"refs"）。複数あれば最初のもの。"""
    for match in _LINK.finditer(body or ""):
        if int(match.group(2)) == task:
            return match.group(1).lower()
    return None


def link_line(task: int, *, partial: bool) -> str:
    return f"{'Refs' if partial else 'Closes'} #{task}"


def with_task_link(body: str, task: int, *, partial: bool) -> str:
    """そのIssueとのつながりの行がなければ、先頭に足す（あれば本文のまま）。"""
    if task_link(body, task) is not None:
        return body
    return link_line(task, partial=partial) + ("\n\n" + body if body else "\n")


@dataclass(frozen=True)
class Task:
    """GitHub Issue。"""

    number: int
    title: str
    url: str
    state: str
    _repository: "Repository" = field(repr=False, compare=False)
    labels: tuple[str, ...] = ()
    assignees: tuple[str, ...] = ()  # 担当者（ログイン名）
    milestone: str | None = None

    @classmethod
    def _from(cls, repository: "Repository", info: _github.IssueInfo) -> "Task":
        return cls(info.number, info.title, info.url, info.state, repository, info.labels, info.assignees,
                   info.milestone)

    def start(self, *, base: str | None = None, ignore_blocked: bool = False) -> "Workspace":
        """作業空間を作る。新しく作るときは、開いている子タスクがあれば止め（親では作業しない）、先に終わるべき
        タスクが開いていれば止める（ignore_blocked で続ける）。"""
        return self._repository._start_workspace(self, base, ignore_blocked=ignore_blocked)


@dataclass(frozen=True)
class Workspace:
    """作業空間：Issue＋作業用ブランチ task/<番号>。コミットはここでだけ行う。"""

    number: int
    branch: str
    base: str
    _repository: "Repository" = field(repr=False, compare=False)

    @property
    def task(self) -> Task:
        return self._repository.task(self.number)

    def stage(self, *paths: str, all: bool = False) -> "StageResult":
        repo = self._repository.git
        repo.add(paths, all=all)
        return StageResult(self.branch, repo.working_tree().staged)

    def commit(self, message: str, *, all: bool = False, amend: bool = False) -> "CommitResult":
        repo = self._repository.git
        tree = repo.working_tree()
        if not (amend or repo.is_merging() or tree.staged or (all and tree.unstaged)):
            add = self._repository._op("task add")
            raise WorkError(ErrorCode.NOTHING_TO_COMMIT, "コミットする変更がありません（ステージされていません）。",
                            hint=f"{add} <パス> か {add} --all でステージしてから実行してください"
                                 "（追跡中のファイルの変更だけなら commit --all でも構いません）。")
        if repo.is_merging():
            # 衝突を解決してのコミット（sync continue の代わり）。印が残ったままなら止める。
            self._repository._refuse_conflict_markers(
                repo.conflict_markers("HEAD") if all else repo.conflict_markers(cached=True))
        sha = repo.commit(message, all=all, amend=amend)
        return CommitResult(self.branch, sha, message)

    def push(self, *, force: bool = False) -> "PushResult":
        repo = self._repository.git
        tree = repo.working_tree()
        repo.push(self.branch, set_upstream=tree.upstream is None, force=force)
        return PushResult(self.branch, f"origin/{self.branch}")

    def submit(self, *, title: str | None = None, partial: bool = False, draft: bool = False) -> "PullRequest":
        return self._repository._submit_workspace(self, title=title, partial=partial, draft=draft)


@dataclass(frozen=True)
class Branch:
    """ブランチ。作業空間でないブランチ（main・develop等）の操作に使う。"""

    name: str
    is_workspace: bool
    base: str | None
    local: bool
    remote: bool
    _repository: "Repository" = field(repr=False, compare=False)

    def submit(self, *, into: str, title: str | None = None, draft: bool = False) -> "PullRequest":
        return self._repository._submit_branch(self, into=into, title=title, draft=draft)

    def delete(self, *, dry_run: bool = False) -> None:
        """dry_runは消せるかを確かめるだけ（消せなければ例外）。"""
        self._repository._delete_branch(self, dry_run=dry_run)


@dataclass(frozen=True)
class PullRequest:
    """PR。値は取得した時点のもの。操作（merge）はPRの番号で、GitHubの最新の内容から判断する。"""

    number: int
    title: str
    url: str
    state: str
    head: str
    base: str
    partial: bool
    _repository: "Repository" = field(repr=False, compare=False)
    author: str = ""
    draft: bool = False

    @classmethod
    def _from(cls, repository: "Repository", info: _github.PullRequestInfo) -> "PullRequest":
        task = workspace_number(info.head)
        partial = task is not None and task_link(info.body, task) == "refs"
        return cls(info.number, info.title, info.url, info.state, info.head, info.base, partial, repository,
                   info.author, info.draft)

    def merge(self, *, ignore_checks: bool = False) -> "MergeResult":
        """ignore_checks：CIが失敗していてもマージする。"""
        return self._repository._merge_pull_request(self.number, ignore_checks=ignore_checks)


@dataclass(frozen=True)
class StageResult:
    branch: str
    staged: tuple[str, ...]


@dataclass(frozen=True)
class CommitResult:
    branch: str
    sha: str
    message: str


@dataclass(frozen=True)
class PushResult:
    branch: str
    remote: str


@dataclass(frozen=True)
class MergeResult:
    number: int
    method: str                      # squash / merge
    closed_issue: int | None
    workspace_rebuilt: bool          # --partialの後、作業空間を作り直したか
    resumed: bool = False            # マージ済みのPRで、途中で止まった後処理だけを行ったか


@dataclass(frozen=True)
class SkippedWorkspace:
    branch: str
    reason: str


@dataclass(frozen=True)
class CleanResult:
    removed: tuple[str, ...]
    skipped: tuple[SkippedWorkspace, ...]
    switched_to: str | None          # 片付けた作業空間にいた場合、移った先
    dry_run: bool


@dataclass(frozen=True)
class DropResult:
    number: int
    branch: str
    lost_commits: tuple[str, ...]    # 作成元に入っていないため失われるコミット（件名）
    closed_pull_requests: tuple[int, ...]
    switched_to: str | None          # 今いる作業空間を捨てた場合、移った先
    issue_closed: bool               # 「対応しない」として閉じたか
    dry_run: bool


@dataclass(frozen=True)
class PullRequestStatus:
    """PRの状態：内容・レビュー・コメント・CIの結果・マージできるか。"""
    number: int
    title: str
    url: str
    state: str
    head: str
    base: str
    author: str
    draft: bool
    body: str
    task: int | None                 # 作業空間のPRなら、そのIssueの番号
    activity: _github.PullRequestActivity


@dataclass(frozen=True)
class RemoveResult:
    """手元の作業空間を消した結果。GitHubのブランチ・PR・Issueはそのまま。"""
    number: int
    branch: str
    base: str                        # 作成元（Issueに記録済み。再開すると同じ作成元になる）
    remote: bool                     # GitHubにブランチがあるか（なければ再開すると作成元の最新から）
    switched_to: str | None          # 今いる作業空間を消した場合、移った先


@dataclass(frozen=True)
class SyncResult:
    branch: str
    merged: tuple[str, ...]          # 取り込んだ（または早送りした）参照。sync continueでは merge／rebase
    extra: object = None             # Hooks.after_sync の戻り値


@dataclass(frozen=True)
class StashResult:
    stashed: bool
    entries: tuple[str, ...]


@dataclass(frozen=True)
class RestoreResult:
    paths: tuple[str, ...]
    staged: bool


@dataclass(frozen=True)
class PullRequestState:
    number: int
    url: str
    state: str


@dataclass(frozen=True)
class Status:
    branch: str | None
    workspace: int | None            # 作業空間ならIssue番号
    base: str | None
    staged: tuple[str, ...]
    unstaged: tuple[str, ...]
    untracked: tuple[str, ...]
    conflicted: tuple[str, ...]
    ahead: int
    behind: int
    merging: bool
    pull_request: PullRequestState | None
    upstream_gone: bool = False      # GitHubのブランチが削除された（別の場所での反映・中止など）
    reviewing: int | None = None     # task review で確認中のPR
    base_behind: int | None = None   # status --fetch：作業空間が作成元より遅れているコミット数


@dataclass(frozen=True)
class TaskSummary:
    number: int
    title: str
    state: str
    url: str
    workspace: bool                  # 手元に作業空間（task/<番号>）があるか
    current: bool                    # 今いる作業空間か
    remote: bool = False             # GitHubに作業空間のブランチがあるか（手元になくても task start で再開できる）
    labels: tuple[str, ...] = ()
    assignees: tuple[str, ...] = ()  # 担当者（ログイン名）
    milestone: str | None = None
    parent: int | None = None        # 親タスク
    subtasks: int = 0                # 子タスクの数
    subtasks_done: int = 0           # そのうち閉じたもの
    blocked_by: int = 0              # 先に終わるべきタスクのうち、開いているものの数


@dataclass(frozen=True)
class TaskStatus:
    """Issue・作業空間・PR（レビュー・コメント・CI）の状態（I-035）。"""
    number: int
    title: str
    state: str
    url: str
    body: str
    workspace: bool
    base: str | None
    pull_request: PullRequestState | None
    activity: _github.PullRequestActivity | None
    remote: bool = False             # GitHubに作業空間のブランチがあるか
    labels: tuple[str, ...] = ()
    assignees: tuple[str, ...] = ()
    comments: tuple[_github.Comment, ...] = ()   # Issueのコメント（作業の記録・申し送り）
    milestone: str | None = None
    parent: "TaskRef | None" = None
    subtasks: tuple["TaskRef", ...] = ()
    blocked_by: tuple["TaskRef", ...] = ()       # 先に終わるべきタスク
    blocking: tuple["TaskRef", ...] = ()         # このタスクを待っているタスク


@dataclass(frozen=True)
class TaskRef:
    """他のタスク（親子・依存の相手）。"""
    number: int
    title: str
    state: str

    @classmethod
    def _from(cls, info: _github.IssueInfo) -> "TaskRef":
        return cls(info.number, info.title, info.state)


@dataclass(frozen=True)
class ReviewResult:
    number: int                      # 確認するPR
    head: str                        # PRのブランチ
    sha: str
    returned_to: str | None = None   # --done で戻ったブランチ


@dataclass(frozen=True)
class LogEntry:
    sha: str
    subject: str
    author: str
    date: str
    pull_request: int | None         # 件名の (#N)
    issue: int | None                # そのPRの作業空間のIssue


@dataclass(frozen=True)
class RevertResult:
    pull_request: int
    task: int
    branch: str
    sha: str | None                  # 衝突で止まった場合はNone
