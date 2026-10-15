from typing import Annotated

from ..._output import run_command
from .finish import render_finish


def command(
    task: Annotated[int, "承認するタスクの番号"],
    message: Annotated[str, "承認に添えるコメント"] = "",
    wait: Annotated[bool, "CIの結果を待つ（待たない場合、実行中なら止まります）"] = True,
    ignore_checks: Annotated[bool, "CIが失敗していても完了する（待たない）"] = False,
    subject: Annotated[str, "取り込むコミットの件名（既定はタスクの題名）"] = "",
    timeout: Annotated[int, "CIを待つ時間の上限（秒）"] = 1800,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """提出を承認し、そのまま完了します（task finish と同じ手順）。

    ecobuild task review で確認中なら、確認の前の場所へ戻ってから完了します。自分の提出は承認できません
    （自分で完了するなら ecobuild task finish）。
    """

    def action(inv):
        return inv.module.approve(task, message, wait=wait, ignore_checks=ignore_checks, subject=subject or None,
                                  timeout=timeout)

    return run_command("task approve", action, render_finish, json_output=json)
