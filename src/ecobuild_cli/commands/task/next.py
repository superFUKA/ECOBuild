from typing import Annotated

from ..._output import run_command
from ._show import task_line


def command(
    count: Annotated[int, "表示する件数"] = 5,
    mine: Annotated[bool, "自分が担当のタスクだけ"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """次にやるタスクを、順位と理由つきで表示します（着手できるものを、期限切れ・今のスプリント・優先度・期限の順に）。"""

    def render(r):
        if not r:
            return "着手できるタスクはありません（ecobuild task list で全体を確認できます）"
        return "\n".join(f"{i}. {task_line(n.task)}\n   理由：{'、'.join(n.reasons) or 'なし（計画の値が未設定）'}"
                         for i, n in enumerate(r, 1))

    return run_command("task next", lambda inv: inv.module.next_tasks(assignee="@me" if mine else None,
                                                                      count=count or None),
                       render, json_output=json)
