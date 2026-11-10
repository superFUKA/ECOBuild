"""文字を見せる。"""
from typing import Annotated, Literal


def part(
    text: Annotated[str, "見せる文字"] = "",
    prefix: Annotated[str, "前に付ける文字"] = "",
    heading: Annotated[bool, "見出しとして見せる"] = False,
    tone: Annotated[Literal["", "muted", "section", "warn", "bad"], "見せ方：muted（補足）・section（節の見出し）・warn（注意の帯）・bad（誤りの帯）"] = "",
) -> None: ...
