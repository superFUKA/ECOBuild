"""文字の並びを、区切りの文字でつないだ1行で書き直す欄（渡すツール・使わせないもの など）。

今の並び（items）を欄に入れておき、書き直すと、区切りでつないだ文字（コマンドがそのまま受ける形）を出す。
"""
from typing import Annotated


def part(
    title: Annotated[str, "見出し"],
    items: Annotated[list[str] | None, "今の並び（まだ無ければ null）"] = None,
    separator: Annotated[str, "区切りの文字"] = ",",
    placeholder: Annotated[str, "空のときの案内"] = "",
) -> None: ...


def on_changed(text: Annotated[str, "今の文字（区切りでつないだ並び）"]) -> None: ...
