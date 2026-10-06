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
    """作業空間の作成元を記録するgitの設定のキー（手元だけ、コミットしない）。"""
    return f"branch.{branch}.ecowork-base"


@dataclass(frozen=True)
class Task:
    """GitHub Issue。"""

    number: int
    title: str
    url: str
    state: str
    _repository: "Repository" = field(repr=False, compare=False)

    @classmethod
    def _from(cls, repository: "Repository", info: _github.IssueInfo) -> "Task":
        return cls(info.number, info.title, info.url, info.state, repository)

    def start(self, *, base: str | None = None) -> "Workspace":
        return self._repository._start_workspace(self, base)


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
            add = self._repository._op("add")
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

    def submit(self, *, title: str | None = None, partial: bool = False) -> "PullRequest":
        return self._repository._submit_workspace(self, title=title, partial=partial)


@dataclass(frozen=True)
class Branch:
    """ブランチ。作業空間でないブランチ（main・develop等）の操作に使う。"""

    name: str
    is_workspace: bool
    base: str | None
    local: bool
    remote: bool
    _repository: "Repository" = field(repr=False, compare=False)

    def submit(self, *, into: str, title: str | None = None) -> "PullRequest":
        return self._repository._submit_branch(self, into=into, title=title)

    def delete(self, *, dry_run: bool = False) -> None:
        """dry_runは消せるかを確かめるだけ（消せなければ例外）。"""
        self._repository._delete_branch(self, dry_run=dry_run)


@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    url: str
    state: str
    head: str
    base: str
    partial: bool
    _repository: "Repository" = field(repr=False, compare=False)

    @classmethod
    def _from(cls, repository: "Repository", info: _github.PullRequestInfo) -> "PullRequest":
        partial = re.search(r"(?im)^refs #\d+", info.body) is not None
        return cls(info.number, info.title, info.url, info.state, info.head, info.base, partial, repository)

    def merge(self) -> "MergeResult":
        return self._repository._merge_pull_request(self)


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
