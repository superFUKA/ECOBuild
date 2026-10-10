from typing import Annotated

from ..._output import run_command, split_list
from ._show import task_line


def command(
    issue: Annotated[int, "Issueの番号"],
    priority: Annotated[str, "優先度（High・Middle・Low）"] = "",
    due: Annotated[str, "期限（YYYY-MM-DD）"] = "",
    estimate: Annotated[str, "見積もり（数値）"] = "",
    sprint: Annotated[str, "スプリント（名前か current）"] = "",
    planned_start: Annotated[str, "開始予定日（YYYY-MM-DD）"] = "",
    planned_end: Annotated[str, "終了予定日（YYYY-MM-DD）"] = "",
    clear: Annotated[str, "消す値（カンマ区切り：priority・due・estimate・sprint・planned_start・planned_end）"] = "",
    stage: Annotated[str, "作業を始める前の段階（planned：計画中、todo：未着手）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスクの計画の値（優先度・期限・見積もり・スプリント・開始予定日・終了予定日）と、作業を始める前の段階
    （計画中・未着手）を設定します。"""
    return run_command("task plan",
                       lambda inv: inv.module.plan_task(issue, priority=priority or None, due=due or None,
                                                        estimate=estimate or None, sprint=sprint or None,
                                                        planned_start=planned_start or None,
                                                        planned_end=planned_end or None, clear=split_list(clear),
                                                        stage=stage or None),
                       lambda r: task_line(r), json_output=json)
