from typing import Annotated

from ..._output import run_command
from ..workspace.close import leave
from ._show import can_answer, render_can
from .finish import render_finish


def command(
    task: Annotated[int, "承認するタスクの番号"],
    message: Annotated[str, "承認に添えるコメント"] = "",
    wait: Annotated[bool, "CIの結果を待つ（待たない場合、実行中なら止まります）"] = True,
    ignore_checks: Annotated[bool, "CIが失敗していても完了する（待たない）"] = False,
    subject: Annotated[str, "取り込むコミットの件名（既定はタスクの題名）"] = "",
    timeout: Annotated[int, "CIを待つ時間の上限（秒）"] = 1800,
    can: Annotated[bool, "実行せずに、今できるかを答える（できなければ、その理由）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """提出を承認し、そのまま完了します（task finish と同じ手順）。

    ecobuild task review の確認用の作業空間があれば、消してから完了します。自分の提出は承認できません
    （自分で完了するなら ecobuild task finish）。
    --can を付けると、承認せずに、今できるか（下書き・権限・自分の提出・作成元との衝突）だけを答えます。
    """
    if can:
        return run_command("task approve", lambda inv: can_answer(inv.module.repository.submission_block(task, "approve")),
                           render_can, json_output=json)

    def action(inv):
        leave(inv.module.root, inv)   # 確認用の作業空間・タスクの作業空間を消すことがある
        return inv.module.repository.approve(task, message, wait=wait, ignore_checks=ignore_checks, subject=subject or None,
                                  timeout=timeout)

    return run_command("task approve", action, render_finish, json_output=json)
