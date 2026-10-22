from typing import Annotated

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_agent import agents as _agents
from ecobuild_agent import children as _children

from ..._output import run_command


def command(id: Annotated[str, "宛先のエージェントの ID（a- で始まる）"],
            *text: Annotated[str, "伝えること（--cancel なら要らない）"],
            cancel: Annotated[str, "まだ届いていない言付け（この番号）を取り消す"] = "",
            replace: Annotated[str, "まだ届いていない言付け（この番号）を取り消して、代わりに伝えることを送る"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """エージェントに言付けを送ります（人から）。

    エージェントの受け箱に入れ、エージェントを動かしている側（係・GUI の窓等）が届けます。作業中でも、返答を止めずに
    次の区切りで届きます。結果の message_id が言付けの番号で、届いたかは agent children --json の messages で
    分かります。まだ届いていなければ --cancel・--replace で取り消せます。
    """
    words = " ".join(text)

    def action(inv):
        if cancel and replace:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "--cancel と --replace は一緒に使えません。")
        record = _agents.load(id)
        if cancel:
            return {"id": record.id, "name": record.name, "message_id": _children.cancel(record, cancel),
                    "cancelled": True}
        if not words.strip():
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "伝えることが空です。")
        if replace:
            _children.cancel(record, replace)
        return {"id": record.id, "name": record.name, "message_id": _children.send(record, words, sender="人")}

    return run_command("agent send", action, render, json_output=json)


def render(r: dict) -> str:
    if r.get("cancelled"):
        return f"「{r['name']}」への言付け {r['message_id']} を取り消しました。"
    return f"「{r['name']}」に送りました（言付け {r['message_id']}）。"
