from typing import Annotated

from ..._output import run_command


def command(
    name: Annotated[str, "ブランチ名（task/ で始まる名前はタスクブランチ専用）"],
    base: Annotated[str, "作成元のブランチ（既定はecobuild.tomlのdefault_base）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスクブランチでないブランチを作り、GitHubへ反映します。"""
    return run_command("branch create", lambda inv: inv.module.repository.create_branch(name, base=base or None),
                       lambda r: f"ブランチ {r.name} を作成しました", json_output=json)
