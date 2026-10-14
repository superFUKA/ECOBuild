from typing import Annotated

from ..._output import run_command


def command(
    all: Annotated[bool, "閉じたマイルストーンも表示する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """マイルストーンの一覧を表示します（期日の順。完了したタスクの数／全体）。"""

    def render(r):
        return "\n".join(f"{m.title}" + (f"（期日 {m.due}）" if m.due else "")
                         + f"  {m.closed_issues}/{m.open_issues + m.closed_issues} 完了"
                         + ("" if m.state == "open" else "（閉じています）") for m in r) or "マイルストーンはありません"

    return run_command("milestone list", lambda inv: inv.module.milestones(closed=all), render, json_output=json)
