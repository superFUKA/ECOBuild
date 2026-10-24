from typing import Annotated

from ecobuild_agent import agents as _agents
from ecobuild_agent import children as _children

from ..._output import run_command
from . import _events


def command(id: Annotated[str, "親のエージェントの ID（a- で始まる。agent list で見られます）"],
            recent: Annotated[int, "1人ごとに、最新の出来事の人向けの行をこの数だけ入れる（recent。GUI の一覧・格子）"] = 0,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """エージェントの子（その子の子も入れ子で）と、その様子を表示します。

    1人ごとに、手伝いか子タスクか・登録・タスクとタスクブランチ・様子（作業中・待機中・止まっている・起動中、その長さ、今して
    いること、届いていない言付け、コンテキストの使用率）・最後の返答。--json の members[] には、submission（最後の
    返答の終わりに係が見た提出）・dirty・ahead・messages（送った言付けと届いたか）・replies・reported・report_at も
    入ります（手元の記録から読みます。GitHub に聞きません）。子の子は members に入れ子で入ります。
    """
    def action(inv):
        record = _agents.load(id)
        return {"id": record.id, "name": record.name,
                "members": _children.listed(record, recent=recent, describe=_events.describe, nested=True)}

    return run_command("agent children", action, render, json_output=json)


def render(r: dict) -> str:
    if not r["members"]:
        return f"「{r['name']}」（{r['id']}）の子はいません。"
    return "\n".join(_lines(r["members"], ""))


def _lines(members: list, indent: str) -> list[str]:
    lines = []
    for m in members:
        task = m.get("task") or {}
        kind = "手伝い" if m.get("kind") == _agents.HELPER else f"子タスク #{task.get('number')}  {m.get('branch') or ''}"
        role = m.get("title") or m.get("registration")
        lines.append(f"{indent}「{m['name']}」（{m['id']}・{role}" + (f"〔登録 {m.get('registration')}〕" if role != m.get("registration") else "")
                     + f"）  {kind}" + ("  報告あり" if m.get("reported") else ""))
        activity = _children.describe_activity(m)
        if activity:
            lines.append(f"{indent}    様子：{activity}")
        if m.get("submission"):
            lines.append(f"{indent}    最後の返答の時点：提出 PR #{m['submission']['pull']}（{m['submission'].get('state')}）")
        if m.get("last_reply"):
            lines.append(f"{indent}    最後の返答：{m['last_reply']}")
        lines += [f"{indent}    | {line.splitlines()[0] if line else ''}" for line in m.get("recent") or ()]
        lines += _lines(m.get("members") or [], indent + "    ")
    return lines
