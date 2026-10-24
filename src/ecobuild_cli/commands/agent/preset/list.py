from typing import Annotated

from ecobuild_agent import registry as _registry
from ecobuild_agent.results import registration_view

from ...._output import run_command
from ..registry import _render


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """プリセットの一覧を表示します（見本と、このPCのプリセット。同じ名前ならこのPCのプリセット）。"""
    return run_command("agent preset list", lambda inv: [registration_view(r) for r in _registry.presets()],
                       lambda r: "\n".join(_render.summary(v) for v in r) or "プリセットはありません", json_output=json)
