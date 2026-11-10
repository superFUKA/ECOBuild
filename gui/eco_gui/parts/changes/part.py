"""変更のあるファイルを、種類ごとに並べて選ぶ。"""
from typing import Annotated


def part(
    status: Annotated[dict, "状態（staged・unstaged・untracked・conflicted：ファイルの並び）"] = {},
    checked: Annotated[list[str], "選んでいるファイル"] = [],
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "変更がないときの文"] = "変更はありません。",
    none_when_empty: Annotated[bool, "チェックが1つもないとき、changed で null を出す（まだ選んでいない、にする）"] = False,
) -> None: ...


def on_changed(paths: Annotated[list[str] | None, "チェックを付けたファイル（none_when_empty なら、1つもないとき null）"]) -> None: ...


def on_selected(path: Annotated[str, "名前を押したファイル（差分を見る）"]) -> None:
    if not path:
        raise ValueError("パスが空です")
