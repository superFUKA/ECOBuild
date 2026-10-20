from pathlib import Path
from typing import Annotated

from ecobuild_agent import app as _app
from ecobuild_agent import team as _team

from ...._output import run_command, to_data
from .. import _events
from . import _forward


def command(nested: Annotated[bool, "下の進行役のチームも入れる（その人の members に。入れ子のまま）"] = False,
            recent: Annotated[int, "1人ごとに、最新の出来事の人向けの行をこの数だけ入れる（recent。GUI の一覧・格子）"] = 0,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """進行役のチーム（作業役・進行役）と、その様子を表示します。

    この作業空間で作った作業役・進行役の、子タスク・タスクブランチ・報告があるか・モデルと、様子（作業中・待機中・
    止まっている、その長さ、届いていない言付け、コンテキストの使用率）、最後の返答の頭。
    止まった・同じところで長く作業中のままの作業役は、agent team restart で起動し直せます。
    """
    args = ["agent", "team", "list", *(["--nested"] if nested else []), *(["--recent", str(recent)] if recent > 0 else [])]
    return run_command("agent team list",
                       lambda inv: _forward.run(inv, args, lambda inv: listed(inv.module.root, nested=nested, recent=recent)),
                       _render, json_output=json)


def listed(root: Path, *, nested: bool = False, recent: int = 0, depth: int = 0) -> dict:
    """進行役の作業空間 root のチーム（JSON にできる形）。nested：下の進行役の members も。recent：最新の行の数。"""
    data = to_data(_team.team(root))
    for member in data["members"]:
        if recent > 0:
            folder = _team.inbox_of(Path(member["path"]))
            member["recent"] = [text for text in map(_events.describe, _app.recent_events(folder)) if text][-recent:]
        if nested and member["role"] == _team.LEAD and depth < 8:   # 8段より深いものは、その進行役で list する
            member["members"] = listed(Path(member["path"]), nested=True, recent=recent, depth=depth + 1)["members"]
    return data


def _render(r, indent: str = "") -> str:
    if not r["members"]:
        return indent + "作業役はまだいません（ecobuild agent team start <名前> --brief … で作ります）。"
    return "\n".join(
        f"{indent}{_team.ROLE_NAMES.get(m['role'], '作業役')}「{m['name']}」 #{m['task']}  {m['branch'] or '（ブランチ不明）'}  "
        f"{'報告あり' if m['reported'] else '報告まだ'}{'  モデル ' + m['model'] if m['model'] else ''}\n{indent}    {_forward.place(m)}"
        + (f"\n{indent}    様子：{_team.describe_activity(m)}" if _team.describe_activity(m) else "")
        + (f"\n{indent}    最後の返答：{m['last_reply']}" if m.get("last_reply") else "")
        + "".join(f"\n{indent}    | {line.splitlines()[0] if line else ''}" for line in m.get("recent") or ())
        + (f"\n{_render(m, indent + '    ')}" if m.get("members") else "")
        for m in r["members"])
