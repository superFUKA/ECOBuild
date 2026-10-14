from typing import Annotated

from ..._output import run_command


def command(
    source: Annotated[str, "移動するファイル"],
    destination: Annotated[str, "移動先（同じProjectの中）"],
    test: Annotated[bool, "ライブラリのソースなら、対応するテストファイルも移動する"] = True,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイルを移動（名前の変更）します。ライブラリのソースなら、対応するテストファイルも移動します。"""

    def action(inv):
        return inv.module.move_file(inv.cwd / source, inv.cwd / destination, test=test)

    def render(r):
        pairs = zip(r.paths[0::2], r.paths[1::2])
        return "移動しました：\n" + "\n".join(f"  {a} → {b}" for a, b in pairs)

    return run_command("file move", action, render, json_output=json)
