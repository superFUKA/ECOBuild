"""ブランチの取り込み・提出の画面の上：このブランチの提出。左に説明、右にボタン1つ。

提出が出ていれば「このブランチの提出を取り込む…」だけ（下書き・処理できない人は灰色と理由）。出ていなくて既定のブランチでなければ
「提出する…」だけ（管理者でも、このブランチを作った人でもなければ灰色と理由）。既定のブランチは提出しない（説明だけ）。
できるかは account show の答え（admin・creators・take_in）を引くだけ（表示だけ。押した操作は ecobuild が確かめる）。
"""
from typing import Annotated, Literal


def part(
    name: Annotated[str, "このブランチ"],
    branches: Annotated[list[dict], "ブランチ（branch list の行。submission・submitted_to を見る）"] = [],
    access: Annotated[dict | None, "アカウントと、できること（account show の結果）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_action(action: Annotated[Literal["submit", "merge"], "押したボタン：submit（提出する…）・merge（このブランチの提出を取り込む…）"]) -> None: ...
