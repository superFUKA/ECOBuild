from typing import Annotated

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """最後に退避した変更を捨てます（stash pop が衝突し、解決した後の片付け等）。"""
    return run_command("stash drop", lambda inv: inv.module.stash_drop(),
                       lambda r: "退避した変更を捨てました", json_output=json)
