from typing import Annotated

from .._output import run_command

AGENT = "read"


def command(
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """モジュールのファイルを一覧します。

    Git が管理しているファイルと、まだ管理していない新しいファイルです（.gitignore の対象は除きます）。JSON は files。
    """
    return run_command("files", lambda inv: {"files": inv.module.repository.files()},
                       lambda r: "\n".join(r["files"]) or "ファイルはありません", json_output=json)
