"""ファイルの木。フォルダーごとに畳め、ファイルを1つ選べる。"""
from typing import Annotated


def part(
    paths: Annotated[list[str], "ファイルのパス（/ で区切る）"],
    selected: Annotated[str | None, "選んでいるファイル"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "空のときの文"] = "ファイルはありません。",
) -> None: ...


def on_selected(path: Annotated[str, "選んだファイル"]) -> None:
    if not path:
        raise ValueError("パスが空です")
