"""押すボタン。"""
from typing import Annotated


def part(
    label: Annotated[str, "ボタンの文字"],
    hint: Annotated[str, "補足"] = "",
    primary: Annotated[bool, "主なボタンとして目立たせる"] = False,
    danger: Annotated[bool, "消す・捨てるなど、戻せない操作として赤く見せる"] = False,
    quiet: Annotated[bool, "目立たせない（枠のないボタン）"] = False,
    answer: Annotated[dict | None, "押した先でできるか（{can, reason}：can のつなぎと同じ形。入力の窓を開くボタン等、包みで灰色にならないもの）。"
                                   "できなければ灰色にして、わけを出す（表示だけ。守りはコマンド）"] = None,
) -> None: ...


def on_pressed() -> None: ...
