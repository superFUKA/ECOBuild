from typing import Annotated

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """マイルストーンごとの進み具合（完了の数・残りの見積もり・期限切れのタスク・期日を過ぎたか）を表示します。"""

    def render(r):
        return "\n".join(f"{m.title}" + (f"（期日 {m.due.isoformat()}）" if m.due else "")
                         + f"  {m.done}/{m.total} 完了・残りの見積もり {m.estimate_remaining:g}"
                         + ("  期日を過ぎています" if m.late else "")
                         + (f"  期限切れ：{', '.join(f'#{n}' for n in m.overdue_tasks)}" if m.overdue_tasks else "")
                         for m in r) or "マイルストーンに入っているタスクはありません"

    return run_command("milestone status", lambda inv: inv.module.milestone_status(), render, json_output=json)
