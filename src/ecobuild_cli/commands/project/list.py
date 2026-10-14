from typing import Annotated

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """Projectの一覧（種類・場所・リンク）を表示します。"""

    def render(r):
        return "\n".join(f"{p.name}（{p.kind}）{p.directory}" + (f"  → {', '.join(p.links)}" if p.links else "")
                         for p in r)

    return run_command("project list", lambda inv: list(inv.module.projects()), render, json_output=json)
