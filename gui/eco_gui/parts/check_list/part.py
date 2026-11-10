"""読んだ一覧（行）から、いくつか選ぶ。文字で絞れる（試験の一覧など）。

どの項目を値にするかは、列の名前で決める。絞り込みの文字は、この部品の中だけの状態（選んだものは変えない）。
"""
from typing import Annotated


def part(
    rows: Annotated[list[dict], "選べるもの（読んだ一覧の行）"] = [],
    value_key: Annotated[str, "値にする項目"] = "name",
    note_key: Annotated[str, "横に小さく見せる項目（空なら出さない）"] = "",
    checked: Annotated[list[str], "選んでいる値"] = [],
    placeholder: Annotated[str, "絞り込みの欄の案内"] = "文字で絞る",
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "空のときの文"] = "ありません",
) -> None: ...


def on_changed(values: Annotated[list[str], "選んでいる値"]) -> None: ...
