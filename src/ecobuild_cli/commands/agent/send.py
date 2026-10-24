from typing import Annotated

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_agent import agents as _agents
from ecobuild_agent import children as _children
from ecobuild_agent import status as _status

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
    AI が起動したエージェント（子）が止まっていれば、係が前の会話の続きから起こして届けます（タスクが閉じている等で
    起こさないときは、そのわけを出します）。
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
        sent = {"id": record.id, "name": record.name, "message_id": _children.send(record, words, sender="人")}
        return {**sent, **_wake(record, inv)}

    return run_command("agent send", action, render, json_output=json)


def _wake(record, inv) -> dict:
    """送った相手が AI の起動した子で止まっていれば、係に起こしてもらう（届けるのは動いている相手だけなので）。
    結果に足すもの：woken・note（起こせない・起こさないわけ）。"""
    if not record.parent or _status.activity(record.folder)["state"] not in (_status.STOPPED, _status.UNKNOWN):
        return {}
    try:
        found = _children.ask_serve(record, ["agent", "wake", record.id], inv.info)
    except EcoBuildError as error:
        return {"woken": False, "note": f"「{record.name}」は止まっているので、まだ届いていません（係に起こしてもらえません"
                                        f"でした：{error.message}）。agent restart {record.id} --resume で起こすと届きます。"}
    return {key: found[key] for key in ("woken", "note") if key in found}


def render(r: dict) -> str:
    if r.get("cancelled"):
        return f"「{r['name']}」への言付け {r['message_id']} を取り消しました。"
    sent = f"「{r['name']}」に送りました（言付け {r['message_id']}）。"
    return f"{sent}\n{r['note']}" if r.get("note") else sent
