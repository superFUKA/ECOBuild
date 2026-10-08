from typing import Annotated

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """担当者ごとの量（開いているタスク・作業中・残りの見積もり・期限切れ）を表示します（親タスクは数えません）。"""

    def render(r):
        return "\n".join(f"{w.assignee or '（担当なし）'}：{w.open} 件（作業中 {w.in_progress}）"
                         f"・残りの見積もり {w.estimate_remaining:g}" + (f"・期限切れ {w.overdue}" if w.overdue else "")
                         + "  " + ", ".join(f"#{n}" for n in w.tasks) for w in r) or "開いているタスクはありません"

    return run_command("task workload", lambda inv: inv.module.workload(), render, json_output=json)
