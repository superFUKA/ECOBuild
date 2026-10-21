"""CLIの誤りの共通の扱い：誤りの種類（code）の一覧、やり直せば通りうるか（retryable）、ヒントがない誤りの既定のヒント。

JSON の error はどのコマンドでも同じ形：{code, message, hint, details, retryable}。
code の一覧は ecobuild --help --json の errors（エージェントが読む）。
"""

from __future__ import annotations

import importlib

from ecobuild.errors import EcoBuildError
from ecobuild.errors import ErrorCode as _ErrorCode


class ErrorCode(_ErrorCode):
    USAGE_ERROR = "usage_error"             # 引数の誤り（終了コード2）
    UNEXPECTED_ERROR = "unexpected_error"   # 予期しない誤り（ECOBuild・拡張の不具合。ログに traceback）
    FAILED = "failed"                       # 理由を残さずに失敗した（終了コード≠0。中の ecobuild・外部のコマンド等）


# 同じ操作をあとでやり直せば通りうるもの（ネットワーク・GitHub の一時的な失敗、使用中、CIの待ち）
RETRYABLE = frozenset({"github_error", "workspace_locked", "in_use", "checks_pending", "no_ci_run"})

# 誤りを出したところがヒントを付けなかったときの、種類ごとの既定のヒント
HINTS = {
    "build_failed": "出力（--json なら error.details）のエラーの行を確かめて直してから、もう一度実行してください。",
    "test_failed": "出力（--json なら error.details）の失敗したテストを確かめてください。",
    "github_error": "ネットワークと gh の認証（gh auth status・ecobuild doctor）を確かめて、もう一度実行してください。",
    "git_error": "出力（--json なら error.details）の git のメッセージを確かめてください（ecobuild status で今の状態）。",
    "task_closed": "閉じたタスクです。続けるなら ecobuild task reopen <番号> で開き直してください。",
    "task_not_found": "番号を ecobuild task list で確かめてください。",
    "unexpected_error": "ECOBuild の不具合の可能性があります。ログ（.ecobuild/logs/ か ECOBuild のログ）の traceback を確かめてください。",
    "failed": "出力とログ（.ecobuild/logs/）を確かめてください。",
}

# 誤りの種類を足す拡張（ErrorCode の子クラスを置くもの）。一覧を作るときに読み込む
_EXTENSIONS = ("ecobuild_agent.errors", "ecobuild_container", "ecobuild_cpp.errors", "ecobuild_cli._self_update")


def retryable(code: str) -> bool:
    return code in RETRYABLE


def hint(code: str, given: str | None) -> str | None:
    """誤りのヒント。付いていなければ種類ごとの既定。"""
    return given or HINTS.get(code)


def unexpected(error: BaseException) -> EcoBuildError:
    """予期しない例外（WorkError でないもの）を、ほかの誤りと同じ形にする。"""
    message = str(error) or type(error).__name__
    return EcoBuildError(ErrorCode.UNEXPECTED_ERROR, f"予期しないエラー（{type(error).__name__}）：{message}",
                         hint=HINTS["unexpected_error"])


def codes() -> list[dict]:
    """誤りの種類の一覧（本体と拡張のもの）。[{code, retryable}]、code の順。"""
    for name in _EXTENSIONS:
        try:
            importlib.import_module(name)
        except ImportError:
            pass
    found: set[str] = set()
    classes = [_ErrorCode.__mro__[-2]]     # 種類の根（ecotask の ErrorCode）から、子クラスをすべて
    while classes:
        each = classes.pop()
        classes += each.__subclasses__()
        found |= {value for key, value in vars(each).items() if key.isupper() and isinstance(value, str)}
    return [{"code": code, "retryable": retryable(code)} for code in sorted(found)]
