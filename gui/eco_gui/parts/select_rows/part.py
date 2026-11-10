"""読んだ一覧（行）から1つ選ぶ欄。どの項目を値・見せる文字にするかは、列の名前で決める。"""
from typing import Annotated


def part(
    title: Annotated[str, "見出し"],
    rows: Annotated[list[dict], "選べるもの（読んだ一覧の行）"] = [],
    value_key: Annotated[str, "値にする項目"] = "name",
    label_key: Annotated[str, "見せる文字にする項目（空なら値だけ）"] = "",
    none_label: Annotated[str, "「選ばない」の文字"] = "（選ばない）",
    value: Annotated[str | None, "選んでいる値"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_changed(value: Annotated[str | None, "選んだ値（選ばないなら null）"]) -> None: ...
