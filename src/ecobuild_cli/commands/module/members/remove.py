from typing import Annotated

from ...._output import run_command


def command(
    user: Annotated[str, "外す人の GitHub のユーザー名"],
    yes: Annotated[bool, "確認せずに実行する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """共同作業者から外します（招待中なら、招待を取り消します）。

    担当しているタスクはそのままです（ecobuild task edit <番号> --remove-assignee で外します）。
    """

    def action(inv):
        inv.confirm(f"{user} を共同作業者から外しますか？（このリポジトリを読めなくなります）")
        return inv.module.repository.remove_member(user)

    return run_command("module members remove", action, lambda r: f"{user} を共同作業者から外しました",
                       json_output=json, yes=yes)
