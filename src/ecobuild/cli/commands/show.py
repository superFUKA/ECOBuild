from typing import Annotated

from .._output import run_command


def command(
    revision: Annotated[str, "コミット（既定：HEAD）"] = "HEAD",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """コミットの内容（変更したファイルと差分）を表示します。"""
    return run_command("show", lambda inv: inv.module.show(revision), lambda r: r, json_output=json)
