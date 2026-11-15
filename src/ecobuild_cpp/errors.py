"""型 cpp のエラーの種類（本体の ErrorCode に足す。値の文字は CLI・GUI が見るので変えない）。"""

from __future__ import annotations

from ecobuild.errors import ErrorCode as _ErrorCode


class ErrorCode(_ErrorCode):
    CPPBUILD_ERROR = "cppbuild_error"
    DEPENDENCY_NOT_FOUND = "dependency_not_found"
    NOT_IN_PROJECT = "not_in_project"
    NOT_LINKABLE = "not_linkable"       # リンク先のモジュールに、リンクできるProject（ライブラリの main）がない
    OLD_FORMAT = "old_format"           # CppBuildの管理ファイルが古い形式（module upgrade で新しくする）
    DEPENDENCY_OLD_FORMAT = "dependency_old_format"   # 依存先の clone の管理ファイルが古い形式（依存先を新しくして deps update）
