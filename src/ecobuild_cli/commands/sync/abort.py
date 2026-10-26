from typing import Annotated

from ..._output import run_command

AGENT = "owner"   # sync のツールで衝突したら、持ち主がツールで終える（sync continue）・やめる（sync abort）


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """止まっている操作（取り込み・作り直し・取り消し・退避した変更の戻し）をやめ、その前に戻します。

    git merge／rebase／revert --abort と同じ。退避した変更の戻しは、戻した変更を捨てます（退避した変更は残っています）。
    """
    return run_command("sync abort", lambda inv: inv.module.abort_sync(),
                       lambda r: "やめて、前の状態に戻しました", json_output=json)
