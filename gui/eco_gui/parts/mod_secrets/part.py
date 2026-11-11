"""CI のシークレットの一覧。名前だけを見せる（値は見せない・入力もしない）。行の「削除…」と、登録の仕方の案内。"""
from typing import Annotated


def part(
    names: Annotated[list[str], "シークレットの名前（ci secret list）"] = [],
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_removed(name: Annotated[str, "削除するシークレットの名前"]) -> None:
    if not name:
        raise ValueError("名前が空です")
