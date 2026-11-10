"""表から1行選ぶ。選ぶと、その行の中身ごと出す（選んだものの状態で、出すボタンを決められる）。行ごとのボタンも置ける。

列の key は、行の中の道筋（task.number）でも書ける。列に format: "time" と書くと、時刻（1970年からの秒、または
文字）を、この PC の時刻の「年-月-日 時:分」で見せる。
"""
from typing import Annotated


def part(
    columns: Annotated[list[dict], "列（{key, label, format}。key は行の中の道筋。format は任意で time）"],
    rows: Annotated[list[dict], "行"],
    key: Annotated[str, "行の ID にする列"] = "id",
    selected: Annotated[str | None, "選んでいる行の ID"] = None,
    selectable: Annotated[bool, "行を選べるか（選べないなら、見せるだけの表）"] = True,
    actions: Annotated[list[dict], "行ごとのボタン（{name, label}）"] = [],
    labels: Annotated[dict, "値の言い換え（列の key → {値: 見せる文字}）"] = {},
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "空のときの文"] = "ありません",
) -> None: ...


def on_selected(id: Annotated[str, "選んだ行の ID"], row: Annotated[dict, "選んだ行の中身"]) -> None:
    if not id:
        raise ValueError("行の ID が要ります")


def on_action(id: Annotated[str, "行の ID"], action: Annotated[str, "押したボタンの名前"]) -> None:
    if not id or not action:
        raise ValueError("行とボタンの名前が要ります")
