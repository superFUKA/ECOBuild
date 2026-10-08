from typing import Annotated

from ..._output import run_command, split_list
from ._show import task_line


def command(
    issue: Annotated[int, "Issueの番号"],
    priority: Annotated[str, "優先度（ボードの選択肢。例：High）"] = "",
    due: Annotated[str, "期限（YYYY-MM-DD）"] = "",
    estimate: Annotated[str, "見積もり（数値）"] = "",
    sprint: Annotated[str, "スプリント（名前か current）"] = "",
    clear: Annotated[str, "消す値（カンマ区切り：priority・due・estimate・sprint）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスクの計画の値（優先度・期限・見積もり・スプリント）を設定します。ボードになければ加えます。"""
    return run_command("task plan",
                       lambda inv: inv.module.plan_task(issue, priority=priority or None, due=due or None,
                                                        estimate=estimate or None, sprint=sprint or None,
                                                        clear=split_list(clear)),
                       lambda r: task_line(r), json_output=json)
