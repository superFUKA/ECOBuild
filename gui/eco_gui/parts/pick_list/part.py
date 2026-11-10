"""文字の並びから、1行を選ぶ（退避した変更の一覧など）。選んだ行は、0 からの番号で出す。"""
from typing import Annotated


def part(
    items: Annotated[list[str], "見せる文字の並び"] = [],
    selected: Annotated[int | None, "選んでいる行の番号（0 から）"] = None,
    numbered: Annotated[bool, "0 からの番号を前に付ける"] = False,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "空のときの文"] = "ありません",
) -> None: ...


def on_selected(index: Annotated[int, "選んだ行の番号（0 から）"]) -> None:
    if index < 0:
        raise ValueError("番号は 0 からです")
