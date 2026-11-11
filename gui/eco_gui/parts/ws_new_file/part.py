"""新しいファイルの入力：場所（フォルダー）と名前（＋ でいくつも）を決める。作るファイルを、打つそばから見せる。

名前に使えない文字・同じ名前の重なり・既にあるファイルは、その場で知らせる。決めたら add で出す（作るのは ecobuild file add）。"""
from typing import Annotated


def part(
    files: Annotated[list[str], "今あるファイル（場所の候補と、既にあるかの確かめに使う）"] = [],
    folder: Annotated[str, "初めに選んでおく場所（空なら一番上）"] = "",
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_add(
    paths: Annotated[list[str], "作るファイル（モジュールからのパス）"],
    test: Annotated[bool, "対応するテストも作るか"] = True,
) -> None:
    if not paths or not all(paths):
        raise ValueError("作るファイルが要ります")


def on_cancel() -> None: ...
