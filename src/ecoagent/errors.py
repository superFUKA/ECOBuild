"""ecoagent のエラー。利用側は`code`で失敗の種類を区別し、`hint`で次の操作を案内する（自分のエラーへ変換してよい）。"""

from __future__ import annotations


class ErrorCode:
    AGENT_NOT_FOUND = "agent_not_found"         # エージェントのコマンドが PATH にない
    DIRECTORY_NOT_FOUND = "directory_not_found"
    NO_TERMINAL = "no_terminal"                 # 新しい画面を開く端末が見つからない（Windows 以外）
    LAUNCH_FAILED = "launch_failed"
    EMPTY_PROMPT = "empty_prompt"               # 話しかける文が空
    ASK_FAILED = "ask_failed"                   # 返答の終わりの印がないまま終わった
    TIMEOUT = "timeout"


class AgentError(Exception):
    """エージェントの操作の失敗。"""

    def __init__(self, code: str, message: str, *, hint: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        return self.message if self.hint is None else f"{self.message}\n{self.hint}"
