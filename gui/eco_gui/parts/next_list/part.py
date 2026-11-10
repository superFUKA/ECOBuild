"""次にやるものの並び。順位と、その順位になった理由を付けて見せる。1つ選べる。"""
from typing import Annotated


def part(
    items: Annotated[list[dict], "並び（{task: {number, title, …}, reasons: [理由]}。先頭が1位）"],
    details: Annotated[list[dict], "題の後ろに小さく見せる task の項目（{key, label}）"] = [],
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "空のときの文"] = "ありません",
) -> None: ...


def on_selected(id: Annotated[str, "選んだものの番号"]) -> None:
    if not id:
        raise ValueError("番号が要ります")
