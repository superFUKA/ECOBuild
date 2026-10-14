"""未コミットの変更を一時的に退避します。"""

from typing import Annotated

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """未コミットの変更（未追跡のファイルを含む）を退避します。戻すには ecobuild stash pop。"""
    return run_command("stash", lambda inv: inv.module.stash(),
                       lambda r: "変更を退避しました" if r.stashed else "退避する変更はありません", json_output=json)
