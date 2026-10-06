"""ecoworkのエラー。利用側は`code`で失敗の種類を区別し、`hint`で次の操作を案内する。"""

from __future__ import annotations


class ErrorCode:
    NOT_IN_WORKSPACE = "not_in_workspace"
    RESERVED_BRANCH_NAME = "reserved_branch_name"
    INVALID_BASE = "invalid_base"
    PROTECTED_BRANCH = "protected_branch"
    DIRTY_WORKING_TREE = "dirty_working_tree"
    MERGE_CONFLICT = "merge_conflict"
    NO_SYNC_IN_PROGRESS = "no_sync_in_progress"
    NOT_FAST_FORWARD = "not_fast_forward"
    LOCAL_CHANGES_WOULD_BE_OVERWRITTEN = "local_changes_would_be_overwritten"
    TASK_NOT_FOUND = "task_not_found"
    TASK_CLOSED = "task_closed"
    CONFLICT_MARKERS = "conflict_markers"
    BRANCH_NOT_FOUND = "branch_not_found"
    NO_PULL_REQUEST = "no_pull_request"
    NOTHING_TO_SUBMIT = "nothing_to_submit"
    NOTHING_TO_COMMIT = "nothing_to_commit"
    PULL_REQUEST_NOT_OPEN = "pull_request_not_open"
    PULL_REQUEST_CONFLICT = "pull_request_conflict"
    CHECKS_FAILED = "checks_failed"
    CHECKS_PENDING = "checks_pending"
    UNFINISHED_WORK = "unfinished_work"
    NO_CI_RUN = "no_ci_run"
    ALREADY_EXISTS = "already_exists"
    REPOSITORY_NOT_FOUND = "repository_not_found"
    COMMITS_WOULD_BE_LOST = "commits_would_be_lost"
    INVALID_ARGUMENT = "invalid_argument"
    TOOL_MISSING = "tool_missing"
    GIT_ERROR = "git_error"
    GITHUB_ERROR = "github_error"


class WorkError(Exception):
    """作業の操作の失敗。"""

    def __init__(self, code: str, message: str, *, hint: str | None = None, details: object = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details

    def __str__(self) -> str:
        return self.message if self.hint is None else f"{self.message}\n{self.hint}"


def operation(command: str, name: str) -> str:
    """ヒントに書く操作。利用側のCLIは操作名（add・sync continue等）と同じ名前のコマンドを持つ約束。

    commandはCLIのコマンド名（例：ecobuild）。空なら操作名だけを書く。
    """
    return f"{command} {name}" if command else name
