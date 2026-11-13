"""テストを作成の入力：テストを置く場所と名前を決める。初めは ecobuild file test <ファイル> --dry-run の場所（組のテスト用 Project の
src/ の同じ構成の場所に <名前>Test.cpp）。作るファイルを打つそばから見せ、既にあれば知らせる（前の GUI と同じ）。

決めたら make で出す（既定の場所のままなら to は空。作るのは ecobuild file test <ファイル> [--to <パス>]）。"""
from typing import Annotated


def part(
    path: Annotated[str, "テストを作るファイル（ライブラリのヘッダー・ソース）"] = "",
    plan: Annotated[dict | None, "既定の場所（ecobuild file test --dry-run の結果：paths）"] = None,
    files: Annotated[list[str], "今あるファイル（場所の候補と、既にあるかの確かめに使う）"] = [],
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_make(to: Annotated[str, "テストを置くパス（既定の場所のままなら空）"] = "") -> None: ...


def on_cancel() -> None: ...
