from typing import Annotated

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """ボードとの接続を外します（ecobuild.toml の [board] を消します。GitHubのボードは消しません）。"""
    return run_command("board unset", lambda inv: inv.module.unset_board(),
                       lambda r: "ボードとの接続を外しました。task commit と task submit で反映してください。",
                       json_output=json)
