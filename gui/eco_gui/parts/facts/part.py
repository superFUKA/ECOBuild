"""名前と値の組を並べて見せる。"""
from typing import Annotated


def part(
    items: Annotated[list[dict], "見せる項目（{key, label}。key は data の中の名前）"],
    data: Annotated[dict, "値（名前 → 値）"] = {},
    labels: Annotated[dict, "値の言い換え（key → {値: 見せる文字}）"] = {},
    tones: Annotated[dict, "値を色の印で見せる（key → {値: 色}。色は ok・warn・bad・info・purple・accent・dim・plain）"] = {},
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...
