"""長い文字（差分・コミットの中身など）を、そのまま見せる。"""
from typing import Annotated


def part(
    text: Annotated[str, "見せる文字"] = "",
    empty_text: Annotated[str, "空のときの文"] = "",
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...
