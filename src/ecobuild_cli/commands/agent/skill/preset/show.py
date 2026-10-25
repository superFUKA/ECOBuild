from typing import Annotated

from ecobuild_agent import skills as _skills
from ecobuild_agent.results import skill_view

from ....._output import run_command
from .. import _render


def command(name: Annotated[str, "このPCのスキルの名前"],
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """このPCのスキルの説明と本文（SKILL.md）を表示します。"""
    return run_command("agent skill preset show", lambda inv: skill_view(_skills.load_preset(name), document=True),
                       lambda r: _render.details(r) + "\n\n" + r.document.rstrip(), json_output=json)
