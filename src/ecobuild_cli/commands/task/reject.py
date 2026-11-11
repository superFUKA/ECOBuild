from typing import Annotated

from ..._output import lines, missing, run_command
from ..workspace.close import leave
from ._show import can_answer, render_can


def command(
    task: Annotated[int, "差し戻すタスクの番号"],
    message: Annotated[str, "直してほしいこと（必須）"] = "",
    can: Annotated[bool, "実行せずに、今できるかを答える（できなければ、その理由）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """提出を差し戻します（修正を依頼します）。タスクは作業中に戻り、作業者が直して task submit で出し直します。

    ecobuild task review の確認用の作業空間があれば消します。
    --can を付けると、差し戻さずに、今できるか（権限・自分の提出）だけを答えます（--message は要りません）。
    """
    if can:
        return run_command("task reject", lambda inv: can_answer(inv.module.repository.submission_block(task, "reject")),
                           render_can, json_output=json)
    if not message:
        return missing("--message", json)

    def action(inv):
        leave(inv.module.root, inv)   # 確認用の作業空間を消すことがある
        return inv.module.repository.reject(task, message)

    return run_command(
        "task reject", action,
        lambda r: lines(f"確認用の作業空間 {r.review_removed} を消しました" if r.review_removed else None,
                        f"#{r.task} を差し戻しました（{r.url}）"),
        json_output=json)
