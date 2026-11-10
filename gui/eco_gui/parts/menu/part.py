"""画面を選ぶメニュー。"""
from typing import Annotated


def part(
    items: Annotated[list[dict], "項目（{id, label}）"],
    current: Annotated[str, "今の項目の id"] = "",
) -> None: ...


def on_selected(id: Annotated[str, "選んだ項目の id"]) -> None:
    if not id:
        raise ValueError("項目の id が要ります")
