"""読んだ一覧（行）から、いくつでもチェックで選ぶ（渡すツール・使えるスキル・起動してよい子 など）。

今の並び（items）のとおりにチェックを付けておき、変えると、選んだ名前の並びを出す。パターン（* や task_* 。
一覧の名前にまとめて当てはまる書き方）も並びに入れられる：パターンに当てはまる名前は、付いたものとして見せる。
"""
from typing import Annotated


def part(
    title: Annotated[str, "見出し"],
    rows: Annotated[list[dict], "選べるもの（読んだ一覧の行）"] = [],
    value_key: Annotated[str, "値にする項目"] = "name",
    label_key: Annotated[str, "名前の横に見せる項目（空なら名前だけ）"] = "",
    hint_key: Annotated[str, "補足として出す項目（マウスを載せると出る。空なら出さない）"] = "",
    items: Annotated[list[str] | None, "今の並び（まだ無ければ null）"] = None,
    patterns: Annotated[bool, "パターン（* 等）を使えるか"] = True,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_changed(items: Annotated[list[str], "選んだ名前・パターンの並び"],
               text: Annotated[str, "同じ並びを、カンマでつないだ文字"]) -> None: ...
