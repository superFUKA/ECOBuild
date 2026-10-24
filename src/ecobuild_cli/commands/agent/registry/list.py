from typing import Annotated

from ecobuild_agent import registry as _registry
from ecobuild_agent.results import registration_view

from ...._output import run_command
from . import _render


def command(in_force: Annotated[bool, "作成元のブランチに取り込まれた登録（起動するのはこちら）を出す"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """モジュールで使えるエージェントの登録の一覧を表示します（見本と、モジュールの登録。同じ名前ならモジュールの登録）。

    ふだんは今いる作業空間（作業ツリー）のものを出し、まだ作成元に取り込まれていないものに印を付けます。
    """
    def action(inv):
        root = inv.module.root
        if in_force:
            return [registration_view(r) for r in _registry.list_registrations(root, in_force=True)]
        waiting = _registry.pending(root)
        return [registration_view(r, pending=r.name in waiting) for r in _registry.list_registrations(root)]

    return run_command("agent registry list", action,
                       lambda r: "\n".join(_render.summary(v) for v in r) or "登録はありません",
                       json_output=json)
