from typing import Annotated

from ..._output import run_command

AGENT = "owner"   # sync のツールで衝突したら、持ち主がツールで終える（sync continue）・やめる（sync abort）


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """止まっている取り込みをやめ、取り込む前に戻します（git merge／rebase --abort と同じ）。"""
    return run_command("sync abort", lambda inv: inv.module.abort_sync(),
                       lambda r: "取り込みをやめました", json_output=json)
