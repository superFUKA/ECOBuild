from typing import Annotated

from ..._output import run_command


def command(
    issue: Annotated[int, "Issueの番号"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """閉じたタスク（Issue）を開き直します。続きは ecobuild task start で作業空間を作ります。"""
    return run_command("task reopen", lambda inv: inv.module.reopen_task(issue),
                       lambda r: f"#{r.number} を開き直しました", json_output=json)
