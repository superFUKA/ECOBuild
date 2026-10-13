from typing import Annotated

from ..._output import missing, run_command


def command(
    message: Annotated[str, "コミットメッセージ（必須）"] = "",
    all: Annotated[bool, "変更したファイルをすべてステージしてからコミットする"] = False,
    amend: Annotated[bool, "直前のコミットをやり直す"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """コミットします（作業空間でのみ）。"""
    if not message:
        return missing("--message", json)

    def action(inv):
        return inv.module.require_workspace("コミット").commit(message, all=all, amend=amend)

    return run_command("task commit", action, lambda r: f"コミットしました：{r.sha[:8]} {r.message}", json_output=json)
