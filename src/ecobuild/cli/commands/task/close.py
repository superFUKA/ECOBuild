from typing import Annotated

from ..._output import run_command


def command(
    issue: Annotated[int, "Issueの番号"],
    not_planned: Annotated[bool, "「対応しない」として閉じる（既定は「完了」）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスク（Issue）を閉じます。作業空間があれば ecobuild task drop か task clean で片付けてください。"""
    return run_command("task close", lambda inv: inv.module.close_task(issue, not_planned=not_planned),
                       lambda r: f"#{r.number} を閉じました", json_output=json)
