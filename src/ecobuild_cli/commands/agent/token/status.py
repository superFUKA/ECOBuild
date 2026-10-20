from typing import Annotated

from ecobuild_agent import tokens as _tokens
from ...._module import PROGRAM
from ...._output import Invocation, execute


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """コンテナの中のエージェントに渡すトークンがあるかを表示します（値は表示しません）。"""
    def action(inv):
        return {"saved": bool(_tokens.load_token()), "path": str(_tokens.token_path())}

    return execute("agent token status", Invocation(json_output=json), action,
                   lambda r: "トークンを覚えています（コンテナの中のエージェントはログインせずに使えます）" if r["saved"]
                   else f"トークンはありません（{PROGRAM} agent token login で作れます。なければ、コンテナの中で一度ログインします）")
