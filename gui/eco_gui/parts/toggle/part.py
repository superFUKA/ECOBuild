"""チェックで、する・しないを選ぶ。"""
from typing import Annotated


def part(
    label: Annotated[str, "横に出す文字"],
    on: Annotated[bool | None, "チェックが付いているか"] = None,
    hint: Annotated[str, "補足"] = "",
) -> None: ...


def on_changed(on: Annotated[bool, "チェックを付けたか"]) -> None: ...
