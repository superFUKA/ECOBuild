from typing import Annotated

from .._gui_command import open_window
from .._output import run_command


def command(
    path: Annotated[str, "ファイル"],
    gui: Annotated[bool, "TortoiseGitで表示する（Windows）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイルの各行を、最後に変えたコミットとともに表示します。"""
    if gui:
        return open_window("blame", (path,), json)
    return run_command("blame", lambda inv: inv.module.blame(path), lambda r: r, json_output=json)
