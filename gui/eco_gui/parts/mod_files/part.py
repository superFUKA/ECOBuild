"""モジュールのファイルの木（ホーム。エクスプローラーと同じもの：git のファイルと、まだ管理していない新しいファイル。.gitignore の対象は除く）。

いちばん上の段から。フォルダーは ▸／▾ でその場で開き、項目の数（空なら「空」）を添える。生成ファイルには印。
ファイルのダブルクリック・Enter・「開く」で、既定のアプリで開く（opened）。
"""
from typing import Annotated


def part(
    files: Annotated[list[str], "ファイル（ecobuild files の files。/ 区切りのモジュールからの相対）"] = [],
    generated: Annotated[list[str] | None, "そのうちの生成ファイル（ecobuild files の generated）"] = None,
    missing: Annotated[list[str] | None, "そのうちの、今はフォルダーにないもの（ecobuild files の missing。出さない）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_opened(path: Annotated[str, "開くファイル（モジュールからの相対）"]) -> None:
    if not path:
        raise ValueError("ファイルが要ります")
