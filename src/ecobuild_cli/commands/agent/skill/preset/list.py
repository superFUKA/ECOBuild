from typing import Annotated

from ecobuild_agent import skills as _skills
from ecobuild_agent.results import skill_view

from ....._output import run_command
from .. import _render


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """このPCのスキルの一覧を表示します。"""
    return run_command("agent skill preset list", lambda inv: [skill_view(s) for s in _skills.presets()],
                       lambda r: "\n".join(_render.summary(v) for v in r) or "このPCのスキルはありません", json_output=json)
