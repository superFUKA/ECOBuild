from typing import Annotated

from .._output import run_command

AGENT = "read"


def command(
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """モジュールのファイルを一覧します。

    Git が管理しているファイルと、まだ管理していない新しいファイルです（.gitignore の対象は除きます）。JSON は files と、
    そのうち今はフォルダーにないもの（消した・動かした。まだコミットしていない）の missing。
    """
    def listed(inv):
        files = inv.module.repository.files()
        return {"files": files, "missing": [name for name in files if not (inv.module.root / name).exists()]}

    def render(r):
        missing = set(r["missing"])
        return "\n".join(name + ("（削除）" if name in missing else "") for name in r["files"]) or "ファイルはありません"

    return run_command("files", listed, render, json_output=json)
