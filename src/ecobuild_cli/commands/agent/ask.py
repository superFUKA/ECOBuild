import sys
from typing import Annotated

from ecobuild_bundle import operator

from ... import build_cli
from ..._operator import prepare as prepare_kit
from ..._output import Invocation, execute, missing


def command(*text: Annotated[str, "話しかける文（省略すると標準入力から読む）"],
            session: Annotated[str, "続ける会話（前の返答の session）。省略すると新しい会話"] = "",
            agent: Annotated[str, "使うエージェントのコマンド（引数は空白で区切る。既定は claude）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """オペレーターに画面を開かずに話しかけ、返答を待ちます（会話の窓のあるアプリ向け）。

    返答の文・会話（session）・途中で実行したコマンドを返します。続けて話すときは --session に前の session を渡します。
    指示・許可は ecobuild agent operator と同じです。許可されていない操作は、聞かれずに断られます。
    """
    message = " ".join(text) or (sys.stdin.read() if not sys.stdin.isatty() else "")
    if not message.strip():
        return missing("話しかける文", json)

    def action(inv):
        prepare_kit(build_cli)
        options = {"command": tuple(agent.split())} if agent.strip() else {}
        return operator.ask(message, session=session or None, **options)

    def render(r):
        done = [f"  $ {a.command}" + ("" if a.ok is not False else "（失敗）") for a in r.actions if a.command]
        return "\n".join([*done, r.text, f"（会話：{r.session}）" if r.session else ""]).strip()

    return execute("agent ask", Invocation(json_output=json), action, render)
