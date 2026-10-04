from typing import Annotated

from .._output import run_command


def command(
    *paths: Annotated[str, "ステージするファイル"],
    all: Annotated[bool, "削除も含めて、すべての変更をステージする"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """変更をステージします（作業空間でのみ）。"""

    def action(inv):
        return inv.module.require_workspace("ステージ").stage(*paths, all=all)

    return run_command("add", action, lambda r: f"ステージ済み：{len(r.staged)} ファイル", json_output=json)
