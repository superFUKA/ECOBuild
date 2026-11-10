"""文字を見せる。"""
from typing import Annotated


def part(
    text: Annotated[str, "見せる文字"] = "",
    prefix: Annotated[str, "前に付ける文字"] = "",
    heading: Annotated[bool, "見出しとして見せる"] = False,
) -> None: ...
