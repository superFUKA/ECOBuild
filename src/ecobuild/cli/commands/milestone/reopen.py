from typing import Annotated

from ..._output import run_command


def command(
    title: Annotated[str, "マイルストーンの題名"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """閉じたマイルストーンを開き直します。"""
    return run_command("milestone reopen", lambda inv: inv.module.edit_milestone(title, state="open"),
                       lambda r: f"マイルストーン {r.title} を開き直しました", json_output=json)
