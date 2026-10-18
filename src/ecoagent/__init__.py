"""ecoagent：AI（コーディングエージェント）を扱うライブラリ。ecobuild 等を知らない（作業空間・モジュールの考えは使う側が持つ）。

- start：指定した場所で、エージェントを新しい端末の画面で起動する。
- ask：画面を開かずに1回話しかけて返答を待つ（会話は session で続ける）。
- kit：決まった道具だけで動くエージェントの一式（指示・許可・フック）を置く。
- guard：シェルのコマンドの関所（フック）。何を通すかは Policy で決める。
- console：今の端末の画面の文字を読む（Windows）。
"""

from . import console, guard, kit
from .conversation import Action, Reply, ask
from .errors import AgentError, ErrorCode
from .launch import DEFAULT_COMMAND, Session, start

__version__ = "0.1.0"

__all__ = ["Action", "AgentError", "DEFAULT_COMMAND", "ErrorCode", "Reply", "Session", "ask", "console", "guard", "kit", "start"]
