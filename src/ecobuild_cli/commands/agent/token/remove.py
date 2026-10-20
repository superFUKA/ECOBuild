from typing import Annotated

from ecobuild_agent import tokens as _tokens
from ...._output import Invocation, execute


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """覚えたトークンを消します（コンテナの中で一度ログインしていれば、そのログインで使えます）。"""
    return execute("agent token remove", Invocation(json_output=json), lambda inv: {"removed": _tokens.forget_token()},
                   lambda r: "トークンを消しました" if r["removed"] else "トークンはありません")
