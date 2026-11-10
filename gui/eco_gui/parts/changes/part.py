"""変更のあるファイルを、種類ごとに並べて選ぶ。"""
from typing import Annotated


def part(
    status: Annotated[dict, "状態（staged・unstaged・untracked・conflicted：ファイルの並び）"] = {},
    checked: Annotated[list[str], "選んでいるファイル"] = [],
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "変更がないときの文"] = "変更はありません。",
) -> None: ...


def on_changed(paths: Annotated[list[str], "チェックを付けたファイル"]) -> None: ...


def on_selected(path: Annotated[str, "名前を押したファイル（差分を見る）"]) -> None:
    if not path:
        raise ValueError("パスが空です")
