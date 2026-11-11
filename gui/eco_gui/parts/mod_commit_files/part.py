"""選んだコミットの中身。上にコミットの説明（だれが・いつ・何を）、下に変更をファイルごとに畳んで見せる（足した行・消した行の数と、色の付いた差分）。"""
from typing import Annotated


def part(
    text: Annotated[str, "コミットの内容（show の出力：説明と差分）"] = "",
    empty_text: Annotated[str, "空のときの文"] = "コミットを選ぶと、中身が出ます。",
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_reload() -> None: ...
