from typing import Annotated

from ecobuild_bundle import team as _team

from ...._output import run_command, to_data
from . import _forward


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """進行役のチーム（作業役・進行役）を表示します。

    この作業空間で作った作業役・進行役の、子タスク・タスクブランチ・報告があるか・モデル。
    """
    return run_command("agent team list", lambda inv: to_data(_team.team(inv.module.root)), _render, json_output=json)


def _render(r) -> str:
    if not r["members"]:
        return "作業役はまだいません（ecobuild agent team start <名前> --brief … で作ります）。"
    return "\n".join(
        f"{_team.ROLE_NAMES.get(m['role'], '作業役')}「{m['name']}」 #{m['task']}  {m['branch'] or '（ブランチ不明）'}  "
        f"{'報告あり' if m['reported'] else '報告まだ'}{'  モデル ' + m['model'] if m['model'] else ''}\n    {_forward.place(m)}"
        for m in r["members"])
