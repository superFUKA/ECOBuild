"""ヘルプ。「使い方」（番号の付いた手順・場所・コマンドのチップ・用語）と「コマンド一覧」（ecobuild help --json の結果）。

手順のコマンドのチップを押すと、コマンド一覧のそのコマンドへ飛ぶ。コマンド一覧は、用途ごとの見出しで分け、
文字と型で絞れる（探した文字に印を付ける）。選んだコマンドは、パンくず・使い方の行（コピーできる）・説明・引数・
オプション・下のコマンド。説明の中の「ecobuild …」は、そのコマンドへの飛び先になる。
タブ・絞り込み・選んでいるコマンドは、この部品の中だけの状態（何も実行しない。読んだものを見せるだけ）。
"""
from typing import Annotated


def part(
    catalog: Annotated[dict, "コマンドの一覧（commands：共通のコマンド、types：型の名前 → {description, commands}）"] = {},
    intro: Annotated[str, "「使い方」の初めの文"] = "",
    steps: Annotated[list[dict], "手順（{title, where, text, commands: [コマンドの名前]}）"] = [],
    terms: Annotated[list[dict], "用語（{term, text}）"] = [],
    categories: Annotated[list[dict], "コマンド一覧の見出し（{title, commands: [一番上のコマンドの名前]}。どれにもないものは「その他」）"] = [],
    first: Annotated[str, "初めに見せるコマンド（task start 等）"] = "",
    type_labels: Annotated[dict, "型の名前の言い換え（cpp → C++ 等）"] = {},
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...
