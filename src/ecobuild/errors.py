"""ECOBuildのエラー。CLIは`code`で失敗の種類を区別し、`hint`で次の操作を案内する。"""

from __future__ import annotations


class ErrorCode:
    NOT_IN_MODULE = "not_in_module"
    INVALID_CONFIG = "invalid_config"
    NOT_IN_WORKSPACE = "not_in_workspace"
    RESERVED_BRANCH_NAME = "reserved_branch_name"
    INVALID_BASE = "invalid_base"
    PROTECTED_BRANCH = "protected_branch"
    DIRTY_WORKING_TREE = "dirty_working_tree"
    GENERATED_FILES_OUTDATED = "generated_files_outdated"
    MERGE_CONFLICT = "merge_conflict"
    NOT_FAST_FORWARD = "not_fast_forward"
    LOCAL_CHANGES_WOULD_BE_OVERWRITTEN = "local_changes_would_be_overwritten"
    TASK_NOT_FOUND = "task_not_found"
    BRANCH_NOT_FOUND = "branch_not_found"
    NO_PULL_REQUEST = "no_pull_request"
    ALREADY_EXISTS = "already_exists"
    CONFIRMATION_REQUIRED = "confirmation_required"
    TOOL_MISSING = "tool_missing"
    GIT_ERROR = "git_error"
    GITHUB_ERROR = "github_error"
    CPPBUILD_ERROR = "cppbuild_error"
    BUILD_FAILED = "build_failed"
    TEST_FAILED = "test_failed"
    RUN_FAILED = "run_failed"


class EcoBuildError(Exception):
    """ECOBuildの操作の失敗。"""

    def __init__(self, code: str, message: str, *, hint: str | None = None, details: object = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details

    def __str__(self) -> str:
        return self.message if self.hint is None else f"{self.message}\n{self.hint}"
