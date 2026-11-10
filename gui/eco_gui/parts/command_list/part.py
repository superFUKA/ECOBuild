"""コマンドの一覧と、選んだコマンドの使い方（ecobuild help --json の結果を見せる）。文字と型で絞れる。

絞り込みの文字・型・選んでいるコマンドは、この部品の中だけの状態（何も実行しない。読んだものを見せるだけ）。
"""
from typing import Annotated


def part(
    catalog: Annotated[dict, "コマンドの一覧（commands：共通のコマンド、types：型の名前 → {description, commands}）"] = {},
    first: Annotated[str, "初めに見せるコマンド（task start 等）"] = "",
    type_labels: Annotated[dict, "型の名前の言い換え（cpp → C++ 等）"] = {},
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...
