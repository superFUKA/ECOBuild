"""押すボタン。"""
from typing import Annotated


def part(
    label: Annotated[str, "ボタンの文字"],
    hint: Annotated[str, "補足"] = "",
    primary: Annotated[bool, "主なボタンとして目立たせる"] = False,
) -> None: ...


def on_pressed() -> None: ...
