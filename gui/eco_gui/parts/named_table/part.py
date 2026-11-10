"""名前の付いたものの表（名前 → 中身の辞書を、1行ずつ見せる）。今使っているものに印を付け、行ごとにボタンを置ける。"""
from typing import Annotated


def part(
    columns: Annotated[list[dict], "列（{key, label}。key は中身の中の名前）"],
    entries: Annotated[dict, "名前 → 中身（列の key → 値）"] = {},
    name_label: Annotated[str, "名前の列の見出し"] = "名前",
    current: Annotated[str | None, "今使っているものの名前"] = None,
    current_mark: Annotated[str, "今使っているものに付ける印"] = "使用中",
    actions: Annotated[list[dict], "行ごとのボタン（{name, label}）"] = [],
    labels: Annotated[dict, "値の言い換え（列の key → {値: 見せる文字}）"] = {},
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "空のときの文"] = "ありません",
) -> None: ...


def on_action(id: Annotated[str, "行の名前"], action: Annotated[str, "押したボタンの名前"]) -> None:
    if not id or not action:
        raise ValueError("行とボタンの名前が要ります")
