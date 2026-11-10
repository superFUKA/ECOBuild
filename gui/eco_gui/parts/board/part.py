"""ボード。カードを、項目の値ごとの列に並べる。カードを選べ、別の列へ移せる。"""
from typing import Annotated


def part(
    columns: Annotated[list[dict], "列（{key, label}）"],
    cards: Annotated[list[dict], "カード（項目の名前 → 値）"],
    group: Annotated[str, "どの項目の値で列に分けるか"] = "stage",
    key: Annotated[str, "カードの ID にする項目"] = "number",
    title: Annotated[str, "カードの題にする項目"] = "title",
    details: Annotated[list[dict], "題の下に小さく見せる項目（{key, label}）"] = [],
    moves: Annotated[list[str], "カードを移せる列（列の key）"] = [],
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "空のときの文"] = "ありません",
) -> None: ...


def on_selected(id: Annotated[str, "選んだカードの ID"]) -> None:
    if not id:
        raise ValueError("カードの ID が要ります")


def on_moved(id: Annotated[str, "移すカードの ID"], to: Annotated[str, "移す先の列の key"]) -> None:
    if not id or not to:
        raise ValueError("カードと、移す先の列が要ります")
