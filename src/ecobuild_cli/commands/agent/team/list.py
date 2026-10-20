from typing import Annotated

from ecobuild_agent import team as _team

from ...._output import run_command, to_data
from . import _forward


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """進行役のチーム（作業役・進行役）と、その様子を表示します。

    この作業空間で作った作業役・進行役の、子タスク・タスクブランチ・報告があるか・モデルと、様子（作業中・待機中・
    止まっている、その長さ、届いていない言付け、コンテキストの使用率）、最後の返答の頭。
    止まった・同じところで長く作業中のままの作業役は、agent team restart で起動し直せます。
    """
    return run_command("agent team list",
                       lambda inv: _forward.run(inv, ["agent", "team", "list"], lambda inv: to_data(_team.team(inv.module.root))),
                       _render, json_output=json)


def _render(r) -> str:
    if not r["members"]:
        return "作業役はまだいません（ecobuild agent team start <名前> --brief … で作ります）。"
    return "\n".join(
        f"{_team.ROLE_NAMES.get(m['role'], '作業役')}「{m['name']}」 #{m['task']}  {m['branch'] or '（ブランチ不明）'}  "
        f"{'報告あり' if m['reported'] else '報告まだ'}{'  モデル ' + m['model'] if m['model'] else ''}\n    {_forward.place(m)}"
        + (f"\n    様子：{_team.describe_activity(m)}" if _team.describe_activity(m) else "")
        + (f"\n    最後の返答：{m['last_reply']}" if m.get("last_reply") else "")
        for m in r["members"])
