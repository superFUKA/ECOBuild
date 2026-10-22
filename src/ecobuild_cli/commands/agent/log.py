import os
from pathlib import Path
from typing import Annotated

import ecobuild_container as container
from ecobuild_agent import app as _app
from ecobuild_agent import status as _status

from ..._output import run_command, usage_error
from . import _events


def command(*id: Annotated[str, "エージェントの ID（a- で始まる。省けば今の作業空間でいちばん新しく起動したエージェント）"],
            follow: Annotated[bool, "終わらずに、新しい出来事を1つずつ出し続ける（止めるには Ctrl+C。--json なら1行1つの JSON）"] = False,
            after: Annotated[int, "この位置より後の出来事だけ（前の結果の next）。既定は最後の --tail 個"] = -1,
            tail: Annotated[int, "表示する出来事の数（新しいほうから。0 ですべて）"] = 50,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """エージェントの出来事（入力・使った道具・返答・返答の終わり）を表示します。

    係が画面なし（アプリ用の起動）で動かしたものの記録です（起動し直しても続けて残ります）。--json の結果は
    events（Claude Code の stream-json の出来事と、係の印 type ecobuild）・next（続きを読む位置：--after に渡す）・
    activity（様子：agent status と同じ項目）。
    """
    if len(id) > 1:
        return usage_error("エージェントの ID は1つだけ書けます。", json)

    def read(inv, cursor: int) -> dict:
        if id:
            from ecobuild_agent import agents
            record = agents.load(id[0])
            folder, place, extra = record.folder, record.workspace, {"id": record.id, "name": record.name}
        else:
            folder, place, extra = folder_of(inv.module.root), inv.module.root, {}
        found, cursor = _app.read_events(folder, after=cursor if cursor >= 0 else None, tail=tail)
        return {**extra, "path": Path(place).as_posix(), "events": found, "next": cursor,
                "activity": _status.activity(folder)}

    if follow:
        return _events.follow("agent log", read, after, json)
    return run_command("agent log", lambda inv: read(inv, after), _events.render, json_output=json)


def folder_of(root: Path) -> Path:
    """この作業空間のエージェントの状態の置き場所（コンテナの中からは自分の置き場所。外からは、いちばん新しく起動した
    エージェント）。"""
    from ecobuild_agent import agents
    own = _status.own_directory()
    if own is not None:
        return own
    if os.environ.get(container.INSIDE):
        return Path(_status.INSIDE)
    found = agents.in_workspace(root)
    return found[-1].folder if found else _status.place(container.name(root))
