from typing import Annotated

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_bundle.tooling import gh_accounts, gh_scopes
from ..._output import lines, run_command
from ..module.members import ROLES

# gh のトークンの権限と、それでできること（足すのは gh auth refresh -s <権限>）
SCOPES = {"repo": "リポジトリの読み書き", "project": "タスク管理（GitHub Projects）", "workflow": "CI のワークフローの変更",
          "delete_repo": "リポジトリの削除"}


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """ログイン中のアカウントと、このモジュールでの役割・できること（管理・提出の取り込み）を表示します。

    提出を取り込めるブランチは、管理者ならすべて、そうでなければ自分が作ったブランチ（既定のブランチを除く）です。
    モジュールの外では、gh の使用中のアカウントと、そのログインが持つ権限（repo・project・workflow・delete_repo）だけを表示します。
    """

    def action(inv):
        try:
            repository = inv.module.repository
        except EcoBuildError as error:
            if error.code != ErrorCode.NOT_IN_MODULE:
                raise
            # モジュールの外：役割はない。だれとして動くか（gh の使用中のアカウント）だけ
            login = next((a["login"] for a in gh_accounts() if a["active"]), "")
            return {"login": login, "role": None, "owner": None, "owner_type": None, "workspace_account": None,
                    "admin": False, "default_base": None, "creators": {}, "take_in": {},
                    "take_in_other": {"allowed": False, "owners": ""},
                    "manage": {"can": False, "reason": "モジュールの中で行います"}, "scopes": gh_scopes() if login else []}
        access = repository.access()
        creators = repository.branch_creators()
        bases = sorted({repository.default_base, *(name for name in creators if not name.startswith("task/"))})
        admin = repository.is_admin()
        return {"login": access.login, "role": access.role, "owner": access.owner, "owner_type": access.owner_type,
                "workspace_account": repository.account,
                "admin": admin, "default_base": repository.default_base,
                # タスクブランチも入れる（子タスクの作成元。親のタスクブランチを作った人が子タスクを反映できる）
                "creators": creators,
                # 提出を処理（承認・差し戻し・取り込み）できるか・できる人。取り込み先のブランチごと（画面が、灰色と理由に使う）。
                # take_in_other は、作った人の記録がないブランチ
                "take_in": {name: {"allowed": repository.can_take_in(name), "owners": repository.take_in_owners(name)} for name in bases},
                "take_in_other": {"allowed": admin, "owners": "管理者"},
                # 管理（ブランチ・メンバー・保護）ができるか・できないわけ（--can の答えと同じ形。画面が、灰色と理由に使う）
                "manage": {"can": admin, "reason": "" if admin else "管理者だけが行えます"},
                # gh の使用中のアカウントのログインが持つ権限（作業空間に結び付けたアカウントのものではない）
                "scopes": gh_scopes()}

    def render(r):
        scopes = "権限（gh のログイン）：" + "、".join(
            f"{text}（{scope}）" + ("" if scope in r["scopes"] else "＝ありません") for scope, text in SCOPES.items())
        if r["role"] is None:  # モジュールの外
            if not r["login"]:
                return "ログインしていません（gh auth login）"
            return lines(f"アカウント：{r['login']}　gh の使用中のアカウント", scopes)
        own = sorted(name for name, who in r["creators"].items()
                     if who.casefold() == r["login"].casefold() and name != r["default_base"] and not name.startswith("task/"))
        return lines(
            f"アカウント：{r['login']}（{ROLES.get(r['role'], r['role'])}）"
            + ("　この作業空間に結び付けたアカウント" if r.get("workspace_account") else "　gh の使用中のアカウント"),
            f"持ち主：{r['owner']}（{'組織' if r['owner_type'] == 'Organization' else '個人のアカウント'}）" if r["owner"] else None,
            "管理（ブランチ・メンバー・保護）：" + ("できます" if r["admin"] else "できません（管理者だけ）"),
            "提出の取り込み：" + ("すべてのブランチ" if r["admin"] else
                               (f"{', '.join(own)}（自分が作ったブランチ）" if own else "できません（取り込み先を作った人と管理者だけ）")),
            scopes,
        )

    return run_command("account show", action, render, json_output=json)
