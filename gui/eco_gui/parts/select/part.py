"""1つ選ぶ欄。"""
from typing import Annotated


def part(
    title: Annotated[str, "見出し"],
    options: Annotated[list[dict], "選べるもの（{value, label}。value が空の文字なら「選ばない」）"],
    value: Annotated[str | None, "選んでいる値"] = None,
) -> None: ...


def on_changed(value: Annotated[str | None, "選んだ値（選ばないなら null）"]) -> None: ...
