from typing import Annotated

from ...._output import missing, run_command


def command(
    issue: Annotated[int, "Issueの番号"],
    field: Annotated[str, "フィールドの名前かID（ecobuild board show で一覧）"] = "",
    value: Annotated[str, "値（単一選択は選択肢の名前、日付は YYYY-MM-DD、スプリントは名前か current）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスクのボード上のフィールドを設定します（例：--field Priority --value High）。"""
    if not field:
        return missing("--field", json)
    if not value:
        return missing("--value", json)
    return run_command("task field set", lambda inv: inv.module.set_task_field(issue, field, value),
                       lambda r: f"#{r.number}：" + ", ".join(f"{k}={v}" for k, v in r.values.items()),
                       json_output=json)
