from typing import Annotated

from ..._output import lines, run_command
from ..module.members import ROLES


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """ログイン中のアカウントと、このモジュールでの役割・できること（管理・提出の取り込み）を表示します。

    提出を取り込めるブランチは、管理者ならすべて、そうでなければ自分が作ったブランチ（既定のブランチを除く）です。
    """

    def action(inv):
        repository = inv.module.repository
        access = repository.access()
        creators = repository.github.branch_creators(repository.root)
        return {"login": access.login, "role": access.role, "owner": access.owner, "owner_type": access.owner_type,
                "admin": repository.is_admin(), "default_base": repository.default_base,
                "creators": {name: who for name, who in creators.items() if not name.startswith("task/")}}

    def render(r):
        own = sorted(name for name, who in r["creators"].items()
                     if who.casefold() == r["login"].casefold() and name != r["default_base"])
        return lines(
            f"アカウント：{r['login']}（{ROLES.get(r['role'], r['role'])}）",
            f"持ち主：{r['owner']}（{'組織' if r['owner_type'] == 'Organization' else '個人のアカウント'}）" if r["owner"] else None,
            "管理（ブランチ・メンバー・保護）：" + ("できます" if r["admin"] else "できません（管理者だけ）"),
            "提出の取り込み：" + ("すべてのブランチ" if r["admin"] else
                               (f"{', '.join(own)}（自分が作ったブランチ）" if own else "できません（取り込み先を作った人と管理者だけ）")),
        )

    return run_command("account show", action, render, json_output=json)
