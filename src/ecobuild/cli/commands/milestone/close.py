from typing import Annotated

from ..._output import run_command


def command(
    title: Annotated[str, "マイルストーンの題名"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """マイルストーンを閉じます（達成した。タスクはそのまま）。"""
    return run_command("milestone close", lambda inv: inv.module.edit_milestone(title, state="closed"),
                       lambda r: f"マイルストーン {r.title} を閉じました"
                                 + (f"（開いているタスクが {r.open_issues} 件あります）" if r.open_issues else ""),
                       json_output=json)
