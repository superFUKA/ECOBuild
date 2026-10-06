from typing import Annotated

from ..._output import run_command


def command(
    issue: Annotated[int, "Issueの番号"],
    title: Annotated[str, "新しい題名"] = "",
    body: Annotated[str, "新しい本文"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスク（Issue）の題名・本文を変えます。"""
    return run_command("task edit", lambda inv: inv.module.edit_task(issue, title=title or None, body=body or None),
                       lambda r: f"#{r.number} {r.title} を更新しました", json_output=json)
