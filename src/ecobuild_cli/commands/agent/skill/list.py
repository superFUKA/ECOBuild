from typing import Annotated

from ecobuild_agent import registry as _registry
from ecobuild_agent import skills as _skills
from ecobuild_agent.results import skill_view

from ...._output import run_command
from . import _render


def command(in_force: Annotated[bool, "作成元のブランチに取り込まれたスキル（エージェントに渡るのはこちら）を出す"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """モジュールのスキルの一覧を、それぞれを使える登録と一緒に表示します。

    ふだんは今いる作業空間（作業ツリー）のものを出し、まだ作成元に取り込まれていない（エージェントに渡らない）ものに
    印を付けます。
    """
    def action(inv):
        root = inv.module.root
        found = _skills.list_skills(root, in_force=in_force)
        waiting = set() if in_force else _skills.pending(root)
        return [skill_view(s, pending=s.name in waiting, used_by=used_by(root, s.name)) for s in found]

    return run_command("agent skill list", action,
                       lambda r: "\n".join(_render.summary(v) for v in r) or "スキルはありません", json_output=json)


def used_by(root, name: str) -> tuple[str, ...]:
    """そのスキルを使える登録の名前（作業ツリーの登録）。"""
    return tuple(r.name for r in _registry.list_registrations(root) if _skills.allowed(r.skills, name))
