from typing import Annotated

from ..._output import missing, optional_argument, run_command


def command(
    *number: Annotated[int, "確認するタスクの番号（--task と同じ）"],
    task: Annotated[int, "確認するタスクの番号"] = 0,
    done: Annotated[bool, "判定を返さずに確認を終え、元のブランチへ戻る"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """他人の提出を手元に取り出して確認します（build・test・run ができます。コミットはできません）。

    確かめたら ecobuild task approve <番号>（承認して完了）か task reject <番号> --message（差し戻し）。
    どちらも元のブランチへ戻ります。
    """
    task = optional_argument(number, task, "--task", json)
    if not task and not done:
        return missing("タスクの番号か --done", json)

    def action(inv):
        return inv.module.end_review() if done else inv.module.review_task(task)

    def render(r):
        if r.returned_to:
            return f"#{r.task or r.number} の確認を終え、{r.returned_to} に戻りました"
        return (f"#{r.task} の提出（{r.sha[:7]}）を取り出しました。\n"
                f"次：確かめたら ecobuild task approve {r.task}（承認して完了）か "
                f"ecobuild task reject {r.task} --message \"…\"（差し戻し）")

    return run_command("task review", action, render, json_output=json)
