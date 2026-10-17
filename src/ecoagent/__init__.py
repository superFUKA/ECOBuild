"""ecoagent：AI（コーディングエージェント）を扱うライブラリ。

今は「指定した場所で、エージェントを新しい端末の画面で起動する」だけ。どのエージェントを使うか・何を渡すか等は
これから決める。ecobuild 等を知らない（作業空間・モジュールの考えは使う側が持つ）。
"""

from .errors import AgentError, ErrorCode
from .launch import DEFAULT_COMMAND, Session, start

__version__ = "0.1.0"

__all__ = ["AgentError", "DEFAULT_COMMAND", "ErrorCode", "Session", "start"]
