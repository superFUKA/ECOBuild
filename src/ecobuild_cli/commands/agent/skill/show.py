from typing import Annotated

from ecobuild_agent import skills as _skills
from ecobuild_agent.results import skill_view

from ...._output import run_command
from . import _render
from .list import used_by


def command(name: Annotated[str, "スキルの名前"],
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """モジュールのスキルの説明と本文（SKILL.md）を表示します（今いる作業空間のもの）。"""
    def action(inv):
        root = inv.module.root
        return skill_view(_skills.load(name, root), document=True, pending=name in _skills.pending(root),
                          used_by=used_by(root, name))

    return run_command("agent skill show", action, lambda r: _render.details(r) + "\n\n" + r.document.rstrip(),
                       json_output=json)
