from typing import Annotated

from .._gui_command import compare
from .._output import optional_argument, run_command


def command(
    *commit: Annotated[str, "コミット（--revision と同じ）"],
    revision: Annotated[str, "コミット（既定：HEAD）"] = "",
    gui: Annotated[bool, "TortoiseGitで表示する（Windows）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """コミットの内容（変更したファイルと差分）を表示します。"""
    revision = optional_argument(commit, revision, "--revision", json) or "HEAD"
    if gui:
        return compare("show", lambda inv: inv.module.repository.show_revisions(revision), json)
    return run_command("show", lambda inv: inv.module.repository.show(revision), lambda r: r, json_output=json)
