from typing import Annotated

from ...._output import missing, run_command


def command(
    issue: Annotated[int, "Issueの番号"],
    field: Annotated[str, "フィールドの名前かID"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスクのボード上のフィールドの値を消します。"""
    if not field:
        return missing("--field", json)
    return run_command("task field clear", lambda inv: inv.module.clear_task_field(issue, field),
                       lambda r: f"#{r.number}：" + (", ".join(f"{k}={v}" for k, v in r.values.items()) or "値なし"),
                       json_output=json)
