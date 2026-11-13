from typing import Annotated

from .._output import run_command

AGENT = "read"


def command(
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """モジュールのファイルを一覧します。

    Git が管理しているファイルと、まだ管理していない新しいファイルです（.gitignore の対象は除きます）。JSON は files と、
    そのうち今はフォルダーにないもの（消した・動かした。まだコミットしていない）の missing、道具が作り直すもの
    （生成ファイル。型が決める：C++ の CMakeLists.txt 等。手で編集しない）の generated、中にファイルのないフォルダー
    （git は記録しない。file add --folder で作ったもの等。いちばん下のもの）の folders。
    """
    def listed(inv):
        files = inv.module.repository.files()
        return {"files": files, "missing": [name for name in files if not (inv.module.root / name).exists()],
                "generated": [name for name in files if inv.module.type.is_generated(name)],
                "folders": inv.module.repository.empty_folders()}

    def render(r):
        missing = set(r["missing"])
        generated = set(r["generated"])
        return "\n".join([name + ("（削除）" if name in missing else "") + ("（生成）" if name in generated else "")
                          for name in r["files"]] + [name + "/（空のフォルダー）" for name in r["folders"]]) or "ファイルはありません"

    return run_command("files", listed, render, json_output=json)
