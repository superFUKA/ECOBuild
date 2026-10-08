from typing import Annotated

from ..._output import run_command, usage_error


def command(
    title: Annotated[str, "マイルストーンの題名"],
    new_title: Annotated[str, "新しい題名"] = "",
    due: Annotated[str, "新しい期日（YYYY-MM-DD）"] = "",
    clear_due: Annotated[bool, "期日を消す"] = False,
    description: Annotated[str, "新しい説明"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """マイルストーンの題名・期日・説明を変えます。"""
    if due and clear_due:
        return usage_error("--due と --clear-due の両方は指定できません。", json)
    return run_command("milestone edit",
                       lambda inv: inv.module.edit_milestone(title, new_title=new_title or None,
                                                             due="" if clear_due else (due or None),
                                                             description=description or None),
                       lambda r: f"マイルストーン {r.title} を更新しました" + (f"（期日 {r.due}）" if r.due else ""),
                       json_output=json)
