from typing import Annotated

from ..._output import run_command

AGENT = "owner"   # sync のツールで衝突したら、持ち主がツールで終える（sync continue）・やめる（sync abort）


def command(
    pipelines: Annotated[bool, "取り込んだ後のパイプラインを走らせる（ecobuild pipeline。--no-pipelines で省く）"] = True,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """衝突を直した後、止まっている操作（取り込み・タスクブランチの作り直し・取り消し・退避した変更の戻し）を完了します。

    直したファイルを登録し、git merge／rebase／revert --continue を行います（残りの取り消しも続けます）。
    退避した変更の戻しは、直したファイルを未コミットの変更にします（退避した変更は ecobuild stash drop まで残ります）。
    """
    return run_command("sync continue", lambda inv: inv.module.continue_sync(progress=inv.info, pipelines=pipelines),
                       lambda r: "続きを完了しました", json_output=json)
