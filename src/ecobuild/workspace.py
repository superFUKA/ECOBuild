"""タスク（GitHub Issue）、作業空間、ブランチ、PR。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from . import _github
from .errors import EcoBuildError, ErrorCode

if TYPE_CHECKING:
    from .module import Module

WORKSPACE_PREFIX = "task/"
_WORKSPACE = re.compile(r"task/(\d+)")


def workspace_branch(number: int) -> str:
    return f"{WORKSPACE_PREFIX}{number}"


def is_workspace_branch(name: str) -> bool:
    return name.startswith(WORKSPACE_PREFIX)


def base_key(branch: str) -> str:
    """作業空間の作成元を記録するgitの設定のキー（手元だけ、コミットしない）。"""
    return f"branch.{branch}.ecobuild-base"


@dataclass(frozen=True)
class Task:
    """GitHub Issue。"""

    number: int
    title: str
    url: str
    state: str
    _module: "Module" = field(repr=False, compare=False)

    @classmethod
    def _from(cls, module: "Module", info: _github.IssueInfo) -> "Task":
        return cls(info.number, info.title, info.url, info.state, module)

    def start(self, *, base: str | None = None) -> "Workspace":
        return self._module._start_workspace(self, base)


@dataclass(frozen=True)
class Workspace:
    """作業空間：Issue＋作業用ブランチ task/<番号>。コミットはここでだけ行う。"""

    number: int
    branch: str
    base: str
    _module: "Module" = field(repr=False, compare=False)

    @property
    def task(self) -> Task:
        return self._module.task(self.number)

    def stage(self, *paths: str, all: bool = False) -> "StageResult":
        repo = self._module._git
        repo.add(paths, all=all)
        return StageResult(self.branch, repo.working_tree().staged)

    def commit(self, message: str, *, all: bool = False, amend: bool = False) -> "CommitResult":
        sha = self._module._git.commit(message, all=all, amend=amend)
        return CommitResult(self.branch, sha, message)

    def push(self, *, force: bool = False) -> "PushResult":
        repo = self._module._git
        tree = repo.working_tree()
        repo.push(self.branch, set_upstream=tree.upstream is None, force=force)
        return PushResult(self.branch, f"origin/{self.branch}")

    def submit(self, *, title: str | None = None, partial: bool = False) -> "PullRequest":
        return self._module._submit_workspace(self, title=title, partial=partial)


@dataclass(frozen=True)
class Branch:
    """ブランチ。作業空間でないブランチ（main・develop等）の操作に使う。"""

    name: str
    is_workspace: bool
    base: str | None
    local: bool
    remote: bool
    _module: "Module" = field(repr=False, compare=False)

    def submit(self, *, into: str, title: str | None = None) -> "PullRequest":
        return self._module._submit_branch(self, into=into, title=title)

    def delete(self) -> None:
        self._module._delete_branch(self)


@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    url: str
    state: str
    head: str
    base: str
    partial: bool
    _module: "Module" = field(repr=False, compare=False)

    @classmethod
    def _from(cls, module: "Module", info: _github.PullRequestInfo) -> "PullRequest":
        partial = re.search(r"(?im)^refs #\d+", info.body) is not None
        return cls(info.number, info.title, info.url, info.state, info.head, info.base, partial, module)

    def merge(self) -> "MergeResult":
        return self._module._merge_pull_request(self)


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
class PullRequestState:
    number: int
    url: str
    state: str


@dataclass(frozen=True)
class ModuleStatus:
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


def not_in_workspace(action: str) -> EcoBuildError:
    return EcoBuildError(
        ErrorCode.NOT_IN_WORKSPACE,
        f"{action}は作業空間（task/<番号>のブランチ）でだけ行えます。",
        hint="ecobuild task start <Issue番号> で作業空間を作るか、作業空間へ切り替えてください。",
    )
