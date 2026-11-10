"""ファイルの木。フォルダーごとに畳め、ファイルかフォルダーを1つ選べる。チェックで、いくつも選べる。"""
from typing import Annotated


def part(
    paths: Annotated[list[str], "ファイルのパス（/ で区切る）"],
    selected: Annotated[str | None, "選んでいるファイル・フォルダー"] = None,
    checked: Annotated[list[str], "チェックを付けたファイル"] = [],
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "空のときの文"] = "ファイルはありません。",
) -> None: ...


def on_selected(path: Annotated[str, "選んだファイル・フォルダー"]) -> None:
    if not path:
        raise ValueError("パスが空です")


def on_changed(paths: Annotated[list[str], "チェックを付けたファイル"]) -> None: ...
