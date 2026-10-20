import os
from pathlib import Path
from typing import Annotated

import ecobuild_container as container
from ecobuild_agent import app as _app
from ecobuild_agent import status as _status

from ..._output import run_command
from . import _events


def command(follow: Annotated[bool, "終わらずに、新しい出来事を1つずつ出し続ける（止めるには Ctrl+C。--json なら1行1つの JSON）"] = False,
            after: Annotated[int, "この位置より後の出来事だけ（前の結果の next）。既定は最後の --tail 個"] = -1,
            tail: Annotated[int, "表示する出来事の数（新しいほうから。0 ですべて）"] = 50,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """この作業空間のエージェントの出来事（入力・使った道具・返答・返答の終わり）を表示します。

    係が画面なし（アプリ用の起動）で動かしたものの記録です。進行役の作業役は agent team log <名前> で。
    """
    def read(inv, cursor: int) -> dict:
        folder = folder_of(inv.module.root)
        found, cursor = _app.read_events(folder, after=cursor if cursor >= 0 else None, tail=tail)
        return {"path": inv.module.root.as_posix(), "events": found, "next": cursor, "activity": _status.activity(folder)}

    if follow:
        return _events.follow("agent log", read, after, json)
    return run_command("agent log", lambda inv: read(inv, after), _events.render, json_output=json)


def folder_of(root: Path) -> Path:
    """この作業空間のエージェントの状態の置き場所（コンテナの中からは、マウントした所）。"""
    return Path(_status.INSIDE) if os.environ.get(container.INSIDE) else _status.directory(container.name(root))
