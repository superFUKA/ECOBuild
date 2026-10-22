from typing import Annotated

from .._gui_command import open_window
from .._output import run_command, usage_error
from .task.diff import render_files

AGENT = "read"


def command(
    *paths: Annotated[str, "このファイル・ディレクトリの差分だけにする"],
    staged: Annotated[bool, "ステージ済みの変更の差分"] = False,
    base: Annotated[bool, "タスクブランチの作成元との差分（PRで出る差分）"] = False,
    stat: Annotated[bool, "変わったファイルごとの行数だけを表示する（JSON は files）"] = False,
    name_only: Annotated[bool, "変わったファイルの名前だけを表示する（JSON は files）"] = False,
    gui: Annotated[bool, "TortoiseGitで表示する（Windows）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """差分を表示します（既定：未コミットでステージしていない変更）。

    --stat・--name-only では、ファイルの一覧（JSON は files：path・status・added・deleted・eol_only。task diff と同じ形）を出します。
    """
    if gui and (stat or name_only):
        return usage_error("--gui は --stat・--name-only と一緒に使えません。", json)
    if gui:
        return open_window("diff", paths, json)
    empty = "作成元からのコミットの差分はありません（未コミットの変更は ecobuild diff）" if base else "差分はありません"
    if stat or name_only:
        return run_command("diff", lambda inv: {"files": inv.module.repository.diff_files(paths, staged=staged, base=base)},
                           lambda r: render_files(r["files"], stat, empty), json_output=json)
    return run_command("diff", lambda inv: inv.module.repository.diff(paths, staged=staged, base=base),
                       lambda r: r or empty, json_output=json)
