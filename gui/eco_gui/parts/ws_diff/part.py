"""差分（コミットの変更・まだコミットしていない変更）を、ファイルごとに畳んで見せる。

ファイルの見出しに、足した行・消した行の数。行は + を緑、- を赤、@@ を青で出す。「すべて開く」「すべて閉じる」「コピー」。"""
from typing import Annotated


def part(
    text: Annotated[str, "差分の文字（ecobuild show・ecobuild diff の結果）"] = "",
    title: Annotated[str | None, "上に出す題（コミットの件名・ファイルの名前）"] = "",
    sha: Annotated[str | None, "コミットの SHA（あれば「SHAをコピー」を出す）"] = "",
    focus: Annotated[str | None, "先に開くファイル・フォルダー（空なら、小さい差分は全部開く）"] = "",
    fill: Annotated[bool, "置いた場所の高さいっぱいに広げる"] = False,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "空のときの文"] = "差分はありません。",
) -> None: ...


def on_copied(what: Annotated[str, "写したもの（sha・text）"]) -> None: ...
