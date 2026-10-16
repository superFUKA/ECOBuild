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
    DEPENDENCY_NOT_RECORDED = "dependency_not_recorded"   # 手元の依存先が記録の版と違う（作業版など。CIは記録の版を使う）
    PROFILE_NOT_FOUND = "profile_not_found"
    NOT_IN_PROJECT = "not_in_project"
    NOT_IN_SOURCE_DIRECTORY = "not_in_source_directory"   # Projectのソースフォルダー（src・include 等）の外：ビルドに入らない
    CHECK_FAILED = "check_failed"
    USAGE_ERROR = "usage_error"
    NOT_ARCHIVED = "not_archived"       # 削除の前に、アーカイブしていない
    REPOSITORY_ARCHIVED = "repository_archived"   # GitHubのリポジトリがアーカイブ（読み取り専用）されている
    NOT_SUPPORTED = "not_supported"     # モジュールの型が対応しない操作
    CLONE_NOT_RECORDED = "clone_not_recorded"     # module forget：その場所は記録にない
    IN_USE = "in_use"                   # 他のプログラム（エディター・端末等）が使っているため、フォルダーを動かせない
    NOT_LINKABLE = "not_linkable"       # リンク先のモジュールに、リンクできるProject（ライブラリの main）がない


class EcoBuildError(WorkError):
    """ECOBuildの操作の失敗。"""
