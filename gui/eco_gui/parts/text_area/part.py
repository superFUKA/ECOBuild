"""何行もの文字を入れる欄（共通の文・説明など、長い文章を書き直す）。"""
from typing import Annotated


def part(
    title: Annotated[str, "見出し"],
    text: Annotated[str | None, "初めの文字（今の中身。まだ無ければ null）"] = None,
    placeholder: Annotated[str, "空のときの案内"] = "",
    rows: Annotated[int, "見せる行の数"] = 10,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_changed(text: Annotated[str, "今の文字"]) -> None: ...
