from typing import Annotated

from ..._output import run_command

AGENT = "owner"   # sync のツールで衝突したら、持ち主がツールで終える（sync continue）・やめる（sync abort）


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """衝突を直した後、止まっている取り込みを完了します。

    直したファイルを登録し、git merge／rebase --continue を行います。
    """
    return run_command("sync continue", lambda inv: inv.module.continue_sync(),
                       lambda r: "取り込みを完了しました", json_output=json)
