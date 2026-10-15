from typing import Annotated

from ..._output import lines, missing, run_command


def command(
    task: Annotated[int, "差し戻すタスクの番号"],
    message: Annotated[str, "直してほしいこと（必須）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """提出を差し戻します（修正を依頼します）。タスクは作業中に戻り、作業者が直して task submit で出し直します。

    ecobuild task review で確認中なら、確認の前の場所へ戻ります。
    """
    if not message:
        return missing("--message", json)
    return run_command(
        "task reject", lambda inv: inv.module.reject(task, message),
        lambda r: lines(f"確認の前の場所 {r.returned_to} に戻りました" if r.returned_to else None,
                        f"#{r.task} を差し戻しました（{r.url}）"),
        json_output=json)
