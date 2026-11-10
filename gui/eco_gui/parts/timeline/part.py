"""日程の帯。行ごとに、始まりから終わりまでの帯と、期限の印を、日付の軸の上に見せる。行を選べる。"""
from typing import Annotated


def part(
    rows: Annotated[list[dict], "行（項目の名前 → 値。日付は YYYY-MM-DD）"],
    key: Annotated[str, "行の ID にする項目"] = "number",
    title: Annotated[str, "行の題にする項目"] = "title",
    start: Annotated[str, "帯の始まりの日付の項目"] = "planned_start",
    end: Annotated[str, "帯の終わりの日付の項目"] = "planned_end",
    due: Annotated[str, "期限の日付の項目"] = "due",
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "空のときの文"] = "ありません",
) -> None: ...


def on_selected(id: Annotated[str, "選んだ行の ID"]) -> None:
    if not id:
        raise ValueError("行の ID が要ります")
