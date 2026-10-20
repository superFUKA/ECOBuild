from typing import Annotated

from ecobuild_agent import app as _app
from ecobuild_agent import status as _status
from ecobuild_agent import team as _team

from ...._output import run_command
from .. import _events
from . import _forward


def command(name: Annotated[str, "作業役の名前（か子タスクの番号）"],
            follow: Annotated[bool, "終わらずに、新しい出来事を1つずつ出し続ける（止めるには Ctrl+C。--json なら1行1つの JSON）"] = False,
            after: Annotated[int, "この位置より後の出来事だけ（前の結果の next）。既定は最後の --tail 個"] = -1,
            tail: Annotated[int, "表示する出来事の数（新しいほうから。0 ですべて）"] = 50,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業役の出来事（入力・使った道具・返答・返答の終わり）を表示します。

    係が画面なし（アプリ用の起動）で動かしている作業役の記録です（起動し直しても続けて残ります）。--json の結果は
    events（Claude Code の stream-json の出来事と、係の印 type ecobuild）・next（続きを読む位置：--after に渡す）・
    activity（様子：team list と同じ項目）。コンテナの中からは係を通して読みます（--follow は2秒ごとに続きを頼みます）。
    """
    def read(inv, cursor: int) -> dict:
        args = ["agent", "team", "log", name, "--tail", str(tail), *(["--after", str(cursor)] if cursor >= 0 else [])]
        return _forward.run(inv, args, lambda inv: events(inv.module.root, name, cursor, tail))

    if follow:
        return _events.follow("agent team log", read, after, json, interval=2.0 if _team.should_forward() else 1.0)
    return run_command("agent team log", lambda inv: read(inv, after), _events.render, json_output=json)


def events(root, name: str, after: int, tail: int) -> dict:
    """進行役の作業空間 root のチームの1人（name）の出来事。"""
    member = _team.find(root, name)
    folder = _team.inbox_of(member.path)
    found, cursor = _app.read_events(folder, after=after if after >= 0 else None, tail=tail)
    return {"name": member.name, "path": member.path.as_posix(), "events": found, "next": cursor,
            "activity": _status.activity(folder)}
