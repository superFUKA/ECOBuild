"""変える前に、人に確かめる。"""
from typing import Annotated


def part(
    message: Annotated[str, "確かめること"],
    preview: Annotated[str, "実行すると起きること"] = "",
    requester: Annotated[str, "だれが頼んだか"] = "",
) -> None: ...


def on_answered(yes: Annotated[bool, "実行してよいか"]) -> None: ...
