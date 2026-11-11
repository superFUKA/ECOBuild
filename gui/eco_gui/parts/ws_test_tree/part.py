"""試験を選ぶ木。読んだ試験の一覧（ecobuild tests）を、まとまりごとの木にして、チェックで選ぶ。

C++ は サブプロジェクト › Suite › Test、Python は フォルダー › ファイル › クラス › 試験。まとまりのチェックで、中の全部を選べる
（一部だけ選んでいるまとまりは、半分の印）。名前で探す（空白で区切ると、全部を含むもの）と、木が絞られて開く。
前に流した結果（✗ ✓ -）を名前の前に出す。全部チェックしたまとまりは、名前1つ（フォルダー・ファイル・Suite の型）で出す。"""
from typing import Annotated


def part(
    rows: Annotated[list[dict], "試験（ecobuild tests の tests：name）"] = [],
    checked: Annotated[list[str], "選んでいるもの（試験の名前か、まとまりの名前）"] = [],
    last: Annotated[dict | None, "前に流した試験の結果（ecobuild test の result：cases の name・status）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "空のときの文"] = "試験はありません。",
) -> None: ...


def on_changed(values: Annotated[list[str], "選んでいるもの（全部選んだまとまりは、その名前1つ）"]) -> None: ...
