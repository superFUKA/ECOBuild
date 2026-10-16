from typing import Annotated

from ecobuild_cli._module import Module
from ..._module_target import full_name
from ..._output import lines, run_command


def command(
    name: Annotated[str, "モジュール名（GitHubのリポジトリ名。所有者/名前 も可）"],
    owner: Annotated[str, "リポジトリの所有者（組織名など。既定は設定の owner、なければログイン中のユーザー）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """アーカイブしたモジュール（GitHubのリポジトリ）を元に戻し、また変更できるようにします。"""

    def action(inv):
        return Module.archive(full_name(name, owner), archived=False)

    return run_command("module unarchive", action, lambda r: lines(
        f"モジュール {r.repository} を元に戻しました（アーカイブを解除）",
        f"リポジトリ：{r.url}",
    ), json_output=json)
