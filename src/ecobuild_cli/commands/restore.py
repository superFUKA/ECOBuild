from typing import Annotated

from .._output import run_command


def command(
    *paths: Annotated[str, "元に戻すファイル"],
    staged: Annotated[bool, "ステージだけを取り消す（ファイルの内容は残す）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """変更を取り消します。"""

    def action(inv):
        return inv.module.restore(*paths, staged=staged)

    return run_command("restore", action,
                       lambda r: f"{'ステージを取り消しました' if r.staged else '元に戻しました'}：{', '.join(r.paths)}",
                       json_output=json)
