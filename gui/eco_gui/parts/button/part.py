"""押すボタン。"""
from typing import Annotated


def part(
    label: Annotated[str, "ボタンの文字"],
    hint: Annotated[str, "補足"] = "",
    primary: Annotated[bool, "主なボタンとして目立たせる"] = False,
    danger: Annotated[bool, "消す・捨てるなど、戻せない操作として赤く見せる"] = False,
    quiet: Annotated[bool, "目立たせない（枠のないボタン）"] = False,
) -> None: ...


def on_pressed() -> None: ...
