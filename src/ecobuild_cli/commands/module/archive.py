from typing import Annotated

from ecobuild_cli._module import Module
from ..._module_target import full_name
from ..._output import lines, run_command


def command(
    name: Annotated[str, "モジュール名（GitHubのリポジトリ名。所有者/名前 も可）"],
    owner: Annotated[str, "リポジトリの所有者（組織名など。既定は設定の owner、なければログイン中のユーザー）"] = "",
    yes: Annotated[bool, "確認せずに実行する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """モジュール（GitHubのリポジトリ）をアーカイブ（読み取り専用）にします。

    ecobuild module unarchive で元に戻せます。

    使わなくなったモジュールを片付ける1段階目です。削除は、アーカイブしたものだけ ecobuild module delete でできます。
    タスク管理の情報は、元に戻したときにそのまま使えるように残します。
    """

    def action(inv):
        target = full_name(name, owner)
        inv.confirm(f"GitHubのモジュール {target} をアーカイブ（読み取り専用）にしますか？")
        return Module.archive(target)

    return run_command("module archive", action, lambda r: lines(
        f"モジュール {r.repository} をアーカイブしました（読み取り専用）",
        f"リポジトリ：{r.url}",
        f"元に戻すには ecobuild module unarchive {r.repository}、削除するには ecobuild module delete {r.repository}",
    ), json_output=json, yes=yes)
