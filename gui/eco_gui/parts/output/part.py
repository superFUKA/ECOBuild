"""動かした道具の出力（ログ）を、届いた順に見せる。"""
from typing import Annotated


def part(
    lines: Annotated[list[str], "出力の行"] = [],
    empty_text: Annotated[str, "まだ出力がないときの文"] = "ここに出力が出ます。",
) -> None: ...
