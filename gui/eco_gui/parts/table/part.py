"""表。行ごとにボタンを置ける。読み込み中・空・誤りの表示を持つ。"""
from typing import Annotated


def part(
    columns: Annotated[list[dict], "列（{key, label}）。key には、入れ子の値への道筋も書ける（submission.base）"],
    rows: Annotated[list[dict], "行（列の key → 値）"] = [],
    key: Annotated[str, "行の ID にする列（道筋も書ける）"] = "id",
    actions: Annotated[list[dict], "行ごとのボタン（{name, label, primary, danger}）"] = [],
    labels: Annotated[dict, "値の言い換え（列の key → {値: 見せる文字}。真偽は true・false、値がないときは空の文字）"] = {},
    tones: Annotated[dict, "値を色の印で見せる（列の key → {値: 色}。色は ok・warn・bad・info・purple・accent・dim・plain）"] = {},
    numbered: Annotated[bool, "先頭に、並びの順番（1 から）を出す"] = False,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "空のときの文"] = "ありません",
) -> None: ...


def on_action(id: Annotated[str, "行の ID"], action: Annotated[str, "押したボタンの名前"]) -> None:
    if not id or not action:
        raise ValueError("行とボタンの名前が要ります")
