from typing import Annotated

from ecobuild_agent import agents as _agents
from ecobuild_agent import children as _children

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """このPCのエージェントの全員を、親子の木で表示します。

    --json の結果は1人1つの並び（起動した順）で、id・name・registration・kind（owner：タスクの持ち主、helper：手伝い）・
    parent（親の ID。人が起動したものは null）・task・workspace・state（作業中・待機中・止まっている・起動中）・since 等です。
    """
    return run_command("agent list", lambda inv: [_children.shown(r) for r in _agents.all_records()], render,
                       json_output=json)


def render(found: list) -> str:
    if not found:
        return "エージェントはいません（ecobuild agent start --as <登録> で起動します）。"
    known = {a["id"] for a in found}
    return "\n".join(_lines([a for a in found if a.get("parent") not in known], found, ""))


def _lines(items: list, found: list, indent: str) -> list[str]:
    lines = []
    for a in items:
        task = a.get("task") or {}
        where = f"#{task.get('number')}" if task.get("number") else ""
        kind = "手伝い" if a.get("kind") == _agents.HELPER else ""
        head = "・".join(x for x in (a.get("registration"), kind, where) if x)
        lines.append(f"{indent}「{a['name']}」（{a['id']}・{head}）  {_children.describe_activity(a) or '不明'}")
        lines.append(f"{indent}    {a.get('path')}")
        lines += _lines([c for c in found if c.get("parent") == a["id"]], found, indent + "    ")
    return lines
