from typing import Annotated

from ..._output import run_command


def command(
    branch: Annotated[str, "実行するブランチ（既定：今いるブランチ）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """今いるブランチ（または --branch）で、CIを手動で実行します（GitHubにpush済みの内容で動きます）。"""
    return run_command("ci run", lambda inv: {"branch": inv.module.ci_dispatch(branch or None)},
                       lambda r: f"{r['branch']} でCIを実行しました（ecobuild ci status で確認）", json_output=json)
