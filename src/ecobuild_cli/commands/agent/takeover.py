import os
from pathlib import Path
from typing import Annotated

import ecobuild_container as container
from ecobuild_agent import agents as _agents
from ecobuild_agent import children as _children

from ..._output import lines, run_command
from ..container._source import source


def command(id: Annotated[str, "引き取るエージェントの ID（a- で始まる）"],
            no_open: Annotated[bool, "止めて会話を返すだけで開かない（GUI がタブで開くとき）"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """係が画面なしで動かしているエージェントを、人が引き取ります。

    係はエージェントを止め（返答を終えさせてから）、同じ会話を人の画面（対話型）で新しく開きます（claude --resume）。
    作業空間・作業はそのままです。話し終えたら画面を閉じ、agent handback <ID> で係に戻します。
    """
    def action(inv):
        record = _agents.load(id)
        result = _children.ask_serve(record, ["agent", "takeover", record.id, "--no-open"], inv.info)
        if no_open or os.environ.get(container.INSIDE):   # コンテナの中からは、このPCの画面を開けない
            return result
        from ..._module import Module
        Module.find(Path(result["path"])).start_agent(program=result["agent"], source=source(), progress=inv.info)
        return {**result, "opened": True}

    return run_command("agent takeover", action, _render, json_output=json)


def _render(r) -> str:
    return lines(
        f"「{r.get('name')}」を引き取りました（係は止めました。会話 {r.get('session')}）。",
        "新しい画面で開きました。" if r.get("opened") else f"人の画面で開くには：{r.get('agent')}（作業空間 {r.get('path')}）",
        f"終わったら画面を閉じ、ecobuild agent handback {r.get('id')} で係に戻してください。",
    )
