from typing import Annotated

from ecobuild_agent import registry as _registry
from ecobuild_agent.results import registration_view

from ...._output import run_command
from . import _render


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """起動できるエージェントの登録の一覧を表示します（見本と、ユーザーの登録。同じ名前ならユーザーの登録）。"""
    def action(inv):
        return [registration_view(r) for r in _registry.list_registrations()]

    return run_command("agent registry list", action,
                       lambda r: "\n".join(_render.summary(v) for v in r) or "登録はありません",
                       json_output=json)
