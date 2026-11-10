"""1行の文字を入れる欄。"""
from typing import Annotated


def part(
    title: Annotated[str, "見出し"],
    text: Annotated[str, "初めの文字"] = "",
    placeholder: Annotated[str, "空のときの案内"] = "",
) -> None: ...


def on_changed(text: Annotated[str, "今の文字"]) -> None: ...


def on_submitted(text: Annotated[str, "決めた文字"]) -> None: ...
