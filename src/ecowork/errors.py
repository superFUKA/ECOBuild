"""ecoworkのエラー。利用側は`code`で失敗の種類を区別し、`hint`で次の操作を案内する。

例外はタスク管理（ecotask）と同じもの（WorkError は ecotask.TaskError）。ErrorCode に作業の流れの分を足す。
"""

from __future__ import annotations

from ecotask.errors import ErrorCode as _TaskErrorCode
from ecotask.errors import TaskError, operation

WorkError = TaskError

__all__ = ["ErrorCode", "WorkError", "operation"]


class ErrorCode(_TaskErrorCode):
    NOT_IN_WORKSPACE = "not_in_workspace"
    RESERVED_BRANCH_NAME = "reserved_branch_name"
    INVALID_BASE = "invalid_base"
    PROTECTED_BRANCH = "protected_branch"
    DIRTY_WORKING_TREE = "dirty_working_tree"
    MERGE_CONFLICT = "merge_conflict"
    NO_SYNC_IN_PROGRESS = "no_sync_in_progress"
    NO_STASH = "no_stash"
    NOT_FAST_FORWARD = "not_fast_forward"
    LOCAL_CHANGES_WOULD_BE_OVERWRITTEN = "local_changes_would_be_overwritten"
    CONFLICT_MARKERS = "conflict_markers"
    BRANCH_NOT_FOUND = "branch_not_found"
    NO_PULL_REQUEST = "no_pull_request"
    NOTHING_TO_SUBMIT = "nothing_to_submit"
    NOTHING_TO_COMMIT = "nothing_to_commit"
    PULL_REQUEST_NOT_OPEN = "pull_request_not_open"
    PULL_REQUEST_CONFLICT = "pull_request_conflict"
    PULL_REQUEST_DRAFT = "pull_request_draft"
    OWN_PULL_REQUEST = "own_pull_request"
    CHECKS_FAILED = "checks_failed"
    CHECKS_PENDING = "checks_pending"
    UNFINISHED_WORK = "unfinished_work"
    NO_CI_RUN = "no_ci_run"
    COMMITS_WOULD_BE_LOST = "commits_would_be_lost"
    GIT_ERROR = "git_error"
