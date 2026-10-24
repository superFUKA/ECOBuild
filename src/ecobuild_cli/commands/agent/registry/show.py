from typing import Annotated

from ecobuild_agent import registry as _registry
from ecobuild_agent.results import registration_view

from ...._output import run_command
from . import _render


def command(name: Annotated[str, "登録の名前"],
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """モジュールの登録の設定と文書（エージェントに渡す agent.md）を表示します（今いる作業空間のもの）。"""
    def action(inv):
        root = inv.module.root
        return registration_view(_registry.load(name, root), document=True, pending=name in _registry.pending(root))

    return run_command("agent registry show", action, lambda r: _render.details(r) + "\n\n" + r.document.rstrip(),
                       json_output=json)
