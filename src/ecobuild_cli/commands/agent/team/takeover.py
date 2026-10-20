import os
from pathlib import Path
from typing import Annotated

import ecobuild_container as container

from ...._output import lines, run_command
from ...container._source import source
from . import _forward


def command(name: Annotated[str, "作業役の名前（か子タスクの番号）"],
            no_open: Annotated[bool, "止めて会話を返すだけで開かない（GUI がタブで開くとき）"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """係が画面なしで動かしている作業役を、人が引き取ります。

    係は作業役を止め（返答を終えさせてから）、同じ会話を人の画面（対話型）で新しく開きます（claude --resume）。
    作業空間・作業はそのままです。話し終えたら画面を閉じ、agent team handback <名前> で係に戻します。
    """
    def action(inv):
        result = _forward.serve(inv, ["agent", "team", "takeover", name])
        if no_open or os.environ.get(container.INSIDE):   # コンテナの中からは、このPCの画面を開けない
            return result
        from ...._module import Module
        Module.find(Path(result["path"])).start_agent(result["agent"].split(), source=source(), progress=inv.info,
                                                      role=result.get("role", ""))
        return {**result, "opened": True}

    return run_command("agent team takeover", action, _render, json_output=json)


def _render(r) -> str:
    return lines(
        f"「{r.get('name')}」を引き取りました（係は止めました。会話 {r.get('session')}）。",
        "新しい画面で開きました。" if r.get("opened") else f"人の画面で開くには：{r.get('agent')}（作業空間 {_forward.place(r)}）",
        f"終わったら画面を閉じ、ecobuild agent team handback {r.get('name')} で係に戻してください。",
    )
