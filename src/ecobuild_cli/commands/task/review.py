from typing import Annotated

from ..._output import missing, optional_argument, run_command


def command(
    *number: Annotated[int, "確認するPRの番号（--pr と同じ）"],
    pr: Annotated[int, "確認するPRの番号"] = 0,
    done: Annotated[bool, "確認を終え、元のブランチへ戻る"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """他人のPRを手元に取り出して確認します（build・test・run ができます。コミットはできません）。"""
    pr = optional_argument(number, pr, "--pr", json)
    if not pr and not done:
        return missing("PRの番号か --done", json)

    def action(inv):
        return inv.module.end_review() if done else inv.module.review(pr)

    def render(r):
        if r.returned_to:
            return f"PR #{r.number} の確認を終え、{r.returned_to} に戻りました"
        return (f"PR #{r.number}（{r.head}、{r.sha[:7]}）を取り出しました。"
                "確認が終わったら ecobuild task review --done")

    return run_command("task review", action, render, json_output=json)
