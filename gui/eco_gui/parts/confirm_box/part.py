"""変える前に、人に確かめる。依頼元は箱（役 dialog）が、この部品の外に出す。"""
from typing import Annotated


def part(
    message: Annotated[str, "確かめること"],
    preview: Annotated[str, "実行すると起きること"] = "",
) -> None: ...


def on_answered(yes: Annotated[bool, "実行してよいか"]) -> None: ...
