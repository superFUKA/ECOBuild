from typing import Annotated

from .._gui_command import open_window
from .._output import run_command


def command(
    *paths: Annotated[str, "このファイル・ディレクトリの差分だけにする"],
    staged: Annotated[bool, "ステージ済みの変更の差分"] = False,
    base: Annotated[bool, "作業空間の作成元との差分（PRで出る差分）"] = False,
    gui: Annotated[bool, "TortoiseGitで表示する（Windows）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """差分を表示します（既定：未コミットでステージしていない変更）。"""
    if gui:
        return open_window("diff", paths, json)
    return run_command("diff", lambda inv: inv.module.diff(paths, staged=staged, base=base),
                       lambda r: r or ("作成元からのコミットの差分はありません（未コミットの変更は ecobuild diff）"
                                       if base else "差分はありません"), json_output=json)
