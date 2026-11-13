"""ecoflow のエラー。利用側は`code`で失敗の種類を区別し、自分のエラーへ変換してよい（ヒントは利用側が足す）。"""

from __future__ import annotations


class ErrorCode:
    INVALID_FLOW = "invalid_flow"       # 定義の誤り（details に誤りの一覧）
    INVALID_INPUT = "invalid_input"     # 実行の入力の誤り（ない名前・足りない入力）
    RUN_NOT_FOUND = "flow_run_not_found"
    RUN_LOCKED = "flow_run_locked"      # ほかのプロセスが動かしている
    INVALID_STATE = "flow_run_state"    # 今の状態ではできない操作（待っていない実行の approve 等）


class FlowError(Exception):
    """流れの操作の失敗。"""

    def __init__(self, code: str, message: str, *, hint: str | None = None, details: object = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details

    def __str__(self) -> str:
        return self.message if self.hint is None else f"{self.message}\n{self.hint}"
