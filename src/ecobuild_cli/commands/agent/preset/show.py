from typing import Annotated

from ecobuild_agent import registry as _registry
from ecobuild_agent.results import registration_view

from ...._output import run_command
from ..registry import _render


def command(name: Annotated[str, "プリセットの名前"],
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """プリセットの設定と文書（agent.md）を表示します。"""
    return run_command("agent preset show", lambda inv: registration_view(_registry.load_preset(name), document=True),
                       lambda r: _render.details(r) + "\n\n" + r.document.rstrip(), json_output=json)
