from typing import Annotated

from ..._output import run_command


def command(
    name: Annotated[str, "削除するブランチ"],
    yes: Annotated[bool, "確認せずに実行する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """作業空間でないブランチを、手元とGitHubから削除します。"""

    def action(inv):
        branch = inv.module.branch(name)
        branch.delete(dry_run=True)  # 消せないものは確認の前に知らせる
        inv.confirm(f"ブランチ {name} を手元とGitHubから削除しますか？")
        branch.delete()
        return {"deleted": name}

    return run_command("branch delete", action, lambda r: f"ブランチ {name} を削除しました",
                       json_output=json, yes=yes)
