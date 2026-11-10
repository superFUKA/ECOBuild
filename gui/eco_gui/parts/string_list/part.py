"""文字の並びを、1行ずつ見せる（退避した変更の一覧など）。"""
from typing import Annotated


def part(
    items: Annotated[list[str], "見せる文字の並び"] = [],
    numbered: Annotated[bool, "0 からの番号を前に付ける"] = False,
    first_mark: Annotated[str, "先頭の行に付ける印（「次に戻すもの」など）"] = "",
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "空のときの文"] = "ありません",
) -> None: ...
