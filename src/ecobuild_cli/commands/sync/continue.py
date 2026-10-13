from typing import Annotated

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """衝突を解決した後、止まっている取り込みを完了します（git merge／rebase --continue と同じ）。"""
    return run_command("sync continue", lambda inv: inv.module.continue_sync(),
                       lambda r: "取り込みを完了しました", json_output=json)
