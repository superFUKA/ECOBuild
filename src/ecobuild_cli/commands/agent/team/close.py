from typing import Annotated

from ecobuild_bundle import team as _team

from ...._output import run_command
from ...workspace.close import render_closed
from . import _forward


def command(name: Annotated[str, "作業役の名前（か子タスクの番号）"],
            discard_local: Annotated[bool, "GitHub にないもの（未コミットの変更・push していないコミット等）も捨てて閉じる"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業役の作業空間を閉じます（場所ごと消します）。

    コンテナも消します。

    取り込みが終わった作業役に使います。GitHub にないもの（未コミットの変更・push していないコミット等）があれば閉じません。
    """
    def action(inv):
        return _forward.run(inv, ["agent", "team", "close", name, *(["--discard-local"] if discard_local else [])],
                            lambda inv: _close(inv))

    def _close(inv):
        member = _team.find(inv.module.root, name)
        return type(inv.module).close_workspace(member.path, discard_local=discard_local)

    return run_command("agent team close", action, _render, json_output=json)


def _render(r) -> str:
    return render_closed(_Closed(r))


class _Closed:
    """render_closed に渡す形（結果は dict）。"""
    def __init__(self, data: dict):
        self.__dict__.update(data)
