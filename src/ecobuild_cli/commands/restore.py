from typing import Annotated

from .._output import run_command


def command(
    *paths: Annotated[str, "元に戻すファイル"],
    staged: Annotated[bool, "ステージだけを取り消す（ファイルの内容は残す）"] = False,
    source: Annotated[str, "この版（コミット）の状態に戻す（タスクブランチで。結果は未コミットの変更になる）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """変更を取り消します。

    ファイルを最後のコミットの状態に戻します（ステージした変更も取り消します）。コミットになかったファイル（追加した
    ファイル）は消えます。--staged ならステージだけを取り消します。

    --source <コミット> を付けると、ファイルを以前の版の状態に戻します（ファイルを省くと全体。その版になかったファイルは
    消えます）。履歴は消さず、戻した結果を ecobuild task commit でコミットします。コミットごと捨てるなら ecobuild task reset。
    """

    def action(inv):
        return inv.module.restore(*paths, staged=staged, source=source or None)

    def render(r):
        if r.source:
            return f"{r.source[:8]} の状態に戻しました：{', '.join(r.paths)}（未コミットの変更です。コミットしてください）"
        return f"{'ステージを取り消しました' if r.staged else '元に戻しました'}：{', '.join(r.paths)}"

    return run_command("restore", action, render, json_output=json)
