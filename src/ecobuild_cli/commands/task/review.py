from typing import Annotated

from ..._output import missing, optional_argument, run_command
from ..workspace.close import leave


def command(
    *number: Annotated[int, "確認するタスクの番号（--task と同じ）"],
    task: Annotated[int, "確認するタスクの番号"] = 0,
    done: Annotated[bool, "判定を返さずに確認を終え、確認用の作業空間を消す"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """他人の提出を確認用の作業空間に取り出して確認します（build・test・run ができます。コミットはできません）。

    確認用の作業空間は元の clone の中の .ecobuild/w/r<PRの番号> です。元の clone のブランチは変わりません。

    確かめたら ecobuild task approve <番号>（承認して完了）か task reject <番号> --message（差し戻し）。
    どちらも確認用の作業空間を消します。
    """
    task = optional_argument(number, task, "--task", json)
    if not task and not done:
        return missing("タスクの番号か --done", json)

    def action(inv):
        if done:
            leave(inv.module.root, inv)   # 確認用の作業空間を消す
            pull_request = inv.module.repository.require_submission(task).number if task else None
            return inv.module.end_review(pull_request)
        module = inv.module.review(task)
        inv.use_module(module)
        return module.reviewed

    def render(r):
        if done:
            return f"#{r.task or r.number} の確認を終え、確認用の作業空間 {r.workspace} を消しました"
        return (f"#{r.task} の提出（{r.sha[:7]}）を確認用の作業空間 {r.workspace} に取り出しました。\n"
                f"次：確かめたら ecobuild task approve {r.task}（承認して完了）か "
                f"ecobuild task reject {r.task} --message \"…\"（差し戻し）")

    return run_command("task review", action, render, json_output=json)
