from typing import Annotated

from ..._output import lines, run_command
from ._show import task_line


def command(
    days: Annotated[int, "この日数以内に期限が来るものも表示する"] = 3,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """期限切れのタスクと、期限が近いタスクを表示します。"""

    def render(r):
        return lines(
            "期限切れ：\n" + "\n".join(f"  {task_line(t)}" for t in r.overdue) if r.overdue else None,
            f"{r.days} 日以内に期限：\n" + "\n".join(f"  {task_line(t)}" for t in r.soon) if r.soon else None,
        ) or f"期限切れ・{r.days} 日以内に期限のタスクはありません"

    return run_command("task overdue", lambda inv: inv.module.deadlines(days=days), render, json_output=json)
