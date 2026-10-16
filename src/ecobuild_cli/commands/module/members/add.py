from typing import Annotated

from ...._output import lines, run_command
from . import ROLES


def command(
    user: Annotated[str, "招待する人の GitHub のユーザー名"],
    role: Annotated[str, "役割（read・triage・write・maintain・admin。既定 write）"] = "write",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """共同作業者に招待します（既に共同作業者なら、役割を変えます）。

    個人のアカウントのリポジトリでは、GitHub の仕様で役割は書き込みだけです（組織のリポジトリなら選べます）。
    招待を受けると加わり、ecobuild module members でタスク管理の情報も共有されます。
    """

    def render(invited):
        return lines(f"{user} を{ROLES.get(role, role)}の共同作業者に招待しました" if invited
                     else f"{user} の役割を{ROLES.get(role, role)}にしました",
                     "次：相手が GitHub の通知・メールから招待を受けたら、ecobuild module members（タスク管理の情報も共有します）"
                     if invited else None)

    return run_command("module members add", lambda inv: inv.module.repository.add_member(user, role), render, json_output=json)
