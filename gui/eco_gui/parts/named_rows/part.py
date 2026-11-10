"""名前の付いた組（名前 → 項目）を、表として見せる。行ごとにボタンを置ける。

コマンドの結果が「名前 → 中身」の辞書で届くもの（ビルド設定など）のための表。行の ID は名前。
"""
from typing import Annotated


def part(
    columns: Annotated[list[dict], "列（{key, label}。key は中身の中の名前）"],
    data: Annotated[dict, "名前 → 中身（列の key → 値）"] = {},
    name_label: Annotated[str, "名前の列の見出し"] = "名前",
    actions: Annotated[list[dict], "行ごとのボタン（{name, label}）"] = [],
    labels: Annotated[dict, "値の言い換え（列の key → {値: 見せる文字}）"] = {},
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "空のときの文"] = "ありません",
) -> None: ...


def on_action(id: Annotated[str, "行の名前"], action: Annotated[str, "押したボタンの名前"]) -> None:
    if not id or not action:
        raise ValueError("行とボタンの名前が要ります")
