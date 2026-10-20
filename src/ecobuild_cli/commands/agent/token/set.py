import sys
from typing import Annotated

import click
from ecobuild_agent import tokens as _tokens

from ...._output import Invocation, execute


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """コンテナの中のエージェントに渡すトークンを覚えます。値は標準入力から読みます（端末なら入力を隠して尋ねます）。

    トークンは claude setup-token（ecobuild agent token login で開けます）が最後に出す sk-ant-oat… の1行です。
    このPCの ECOBUILD_HOME に置き、コンテナの中でエージェントを起動するときに CLAUDE_CODE_OAUTH_TOKEN で渡します。
    """
    def action(inv):
        value = click.prompt("トークン", hide_input=True, err=True) if sys.stdin.isatty() else sys.stdin.read()
        return {"saved": True, "path": str(_tokens.save_token(value))}

    return execute("agent token set", Invocation(json_output=json), action,
                   lambda r: "トークンを覚えました。コンテナの中のエージェントはログインせずに使えます")
