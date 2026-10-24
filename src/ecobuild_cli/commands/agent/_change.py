"""モジュールのエージェントの設定（登録・共通の文。.ecobuild/agents/）を変える操作の共通の手順。"""

from ecobuild.errors import EcoBuildError, ErrorCode


def in_task_branch(inv, message: str, change):
    """タスクブランチでだけ change(module) を行い、書いた ECOBuild 自身のファイルを message でコミットする。
    (change の戻り値, コミットした版〔しなければ空〕) を返す。起動したエージェントに効くのは、提出して作成元に
    取り込まれてから。"""
    module = inv.module
    if module.repository.current_task_branch() is None:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                            "モジュールのエージェントの設定は、タスクブランチで変えます（コミットして PR で取り込みます）。",
                            hint="ecobuild task start でタスクブランチを作ってから、その作業空間で実行してください。")
    before = module.own_changes()
    result = change(module)
    committed = module.commit_own_changes(message, before)
    return result, committed.sha if committed else ""
