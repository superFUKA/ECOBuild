from typing import Annotated

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """最後に退避した変更を戻します。"""
    return run_command("stash pop", lambda inv: inv.module.stash_pop(),
                       lambda r: "退避した変更を戻しました", json_output=json)
