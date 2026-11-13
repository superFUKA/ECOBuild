"""コミットの欄：コミットメッセージ、「直前のコミットを修正」、コミットのボタン（選んだファイルの数を出す）。

メッセージが空のあいだ・選んだファイルがなく修正でもないあいだは、ボタンを押せない。コミットが済んで text が空で届いたら、欄を空にする。
修正でファイルを選んでいなければ all、Push 済みのコミットを修正するなら pushed を付けて出す（確かめる・強制Push の案内は画面のつなぎ）。"""
from typing import Annotated


def part(
    text: Annotated[str | None, "コミットメッセージ（共有の値。空で届いたら欄を空にする）"] = None,
    amend: Annotated[bool | None, "「直前のコミットを修正」に印が付いているか"] = None,
    checked: Annotated[list[str] | None, "コミットするファイル（数をボタンに出す）"] = None,
    status: Annotated[dict, "状態（ecobuild status：task・reviewing・ahead・変更の並び）。タスクブランチでない・確認中は、コミットを押せない"] = {},
) -> None: ...


def on_changed(text: Annotated[str, "今のメッセージ"]) -> None: ...


def on_amend(on: Annotated[bool, "印を付けたか"]) -> None: ...


def on_commit(
    amend: Annotated[bool, "「直前のコミットを修正」に印が付いているか"] = False,
    all: Annotated[bool, "修正で、ファイルを選んでいない（すべての変更を直前のコミットに含める。確かめてから）"] = False,
    pushed: Annotated[bool, "修正するコミットは Push 済み（修正の後は強制Push で送る）"] = False,
) -> None: ...
