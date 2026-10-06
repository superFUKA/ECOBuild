"""ECOBuildのエラー。CLIは`code`で失敗の種類を区別し、`hint`で次の操作を案内する。

作業の進め方の失敗は ecowork.WorkError で届く。EcoBuildError はその子で、ECOBuild独自の種類を足す。
"""

from __future__ import annotations

from ecowork.errors import ErrorCode as _WorkErrorCode
from ecowork.errors import WorkError


class ErrorCode(_WorkErrorCode):
    NOT_IN_MODULE = "not_in_module"
    INVALID_CONFIG = "invalid_config"
    GENERATED_FILES_OUTDATED = "generated_files_outdated"
    CONFIRMATION_REQUIRED = "confirmation_required"
    CPPBUILD_ERROR = "cppbuild_error"
    BUILD_FAILED = "build_failed"
    TEST_FAILED = "test_failed"
    RUN_FAILED = "run_failed"
    PROJECT_NOT_FOUND = "project_not_found"
    INVALID_CONFIGURATION = "invalid_configuration"
    FILE_NOT_FOUND = "file_not_found"
    DEPENDENCY_NOT_FOUND = "dependency_not_found"
    PROFILE_NOT_FOUND = "profile_not_found"
    NOT_IN_PROJECT = "not_in_project"
    CHECK_FAILED = "check_failed"
    USAGE_ERROR = "usage_error"


class EcoBuildError(WorkError):
    """ECOBuildの操作の失敗。"""
