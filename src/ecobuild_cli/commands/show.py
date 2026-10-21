from typing import Annotated

from .._gui_command import compare
from .._output import optional_argument, run_command, usage_error
from .task.diff import render_files


def command(
    *commit: Annotated[str, "コミット（--revision と同じ）"],
    revision: Annotated[str, "コミット（既定：HEAD）"] = "",
    stat: Annotated[bool, "変わったファイルごとの行数だけを表示する（JSON は files）"] = False,
    name_only: Annotated[bool, "変わったファイルの名前だけを表示する（JSON は files）"] = False,
    gui: Annotated[bool, "TortoiseGitで表示する（Windows）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """コミットの内容（変更したファイルと差分）を表示します。

    --stat・--name-only では、ファイルの一覧（JSON は files：path・status・added・deleted・eol_only。task diff と同じ形）を出します。
    """
    revision = optional_argument(commit, revision, "--revision", json) or "HEAD"
    if gui and (stat or name_only):
        return usage_error("--gui は --stat・--name-only と一緒に使えません。", json)
    if gui:
        return compare("show", lambda inv: inv.module.repository.show_revisions(revision), json)
    if stat or name_only:
        return run_command("show", lambda inv: {"files": inv.module.repository.show_files(revision)},
                           lambda r: render_files(r["files"], stat, "変わったファイルはありません"), json_output=json)
    return run_command("show", lambda inv: inv.module.repository.show(revision), lambda r: r, json_output=json)
