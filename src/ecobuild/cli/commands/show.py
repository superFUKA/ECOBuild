from typing import Annotated

from .._output import optional_argument, run_command


def command(
    *commit: Annotated[str, "コミット（--revision と同じ）"],
    revision: Annotated[str, "コミット（既定：HEAD）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """コミットの内容（変更したファイルと差分）を表示します。"""
    revision = optional_argument(commit, revision, "--revision", json) or "HEAD"
    return run_command("show", lambda inv: inv.module.show(revision), lambda r: r, json_output=json)
