"""文字の並びから1つ選ぶ欄（ブランチの名前・版の番号など、読んだ結果が文字の並びのもの）。"""
from typing import Annotated


def part(
    title: Annotated[str, "見出し"],
    options: Annotated[list[str], "選べるもの（読んだ文字の並び）"] = [],
    none_label: Annotated[str, "「選ばない」の文字"] = "（選ばない）",
    value: Annotated[str | None, "選んでいる値"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_changed(value: Annotated[str | None, "選んだ値（選ばないなら null）"]) -> None: ...
