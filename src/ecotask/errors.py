"""ecotaskのエラー。利用側は`code`で失敗の種類を区別し、`hint`で次の操作を案内する。

TaskError は ecowork・ecobuild でも使う例外の根（ecowork.WorkError は同じもの）。ErrorCode は利用側が広げる。
"""

from __future__ import annotations


class ErrorCode:
    TASK_NOT_FOUND = "task_not_found"
    TASK_CLOSED = "task_closed"
    TASK_BLOCKED = "task_blocked"            # 先に終わるべきタスク（blocked by）が開いている
    OPEN_SUBTASKS = "open_subtasks"          # 子タスクが開いている（親は終了できない）
    MILESTONE_NOT_FOUND = "milestone_not_found"
    NO_BOARD = "no_board"                    # ボード（GitHub Projects）をつないでいない
    BOARD_PERMISSION = "board_permission"    # ghのトークンに project の権限がない
    FIELD_NOT_FOUND = "field_not_found"
    NOT_ON_BOARD = "not_on_board"            # タスクがボードにない
    STAGE_FIELD = "stage_field"              # 作業の段階は操作で変わる（手では設定しない）
    BOARD_SHARED = "board_shared"            # ボードが他のリポジトリと共有されている（専用でない）
    ALREADY_EXISTS = "already_exists"
    REPOSITORY_NOT_FOUND = "repository_not_found"
    INVALID_ARGUMENT = "invalid_argument"
    TOOL_MISSING = "tool_missing"
    GITHUB_ERROR = "github_error"


class TaskError(Exception):
    """タスク管理（と、それを使う作業の流れ）の操作の失敗。"""

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
