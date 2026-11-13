"""CI のシークレットの一覧。名前だけを見せる（値は見せない・入力もしない）。行の「削除…」と、登録の仕方の案内。

管理者でない人（admin が偽）には「削除…」を灰色と理由「管理者だけが行えます」。
"""
from typing import Annotated


def part(
    names: Annotated[list[str], "シークレットの名前（ci secret list）"] = [],
    admin: Annotated[bool | None, "このモジュールの管理者か（account show の admin。分からないあいだは null）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_removed(name: Annotated[str, "削除するシークレットの名前"]) -> None:
    if not name:
        raise ValueError("名前が空です")
