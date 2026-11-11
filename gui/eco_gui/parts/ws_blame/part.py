"""注釈履歴：ファイルの各行を、最後に変えたコミット（短い SHA・だれが・いつ）と並べて見せる（ecobuild blame の結果）。

同じコミットが続く行は、初めの行にだけコミットを書く。コミットごとに帯の色を分け、選んだコミットの行を強調する。
絞り込み（コミット・人・行の文字）。SHA を押すと、そのコミットを opened で出す（変更を見る窓を開くのは、画面のつなぎ）。
"""
from typing import Annotated


def part(
    text: Annotated[str | None, "注釈履歴（ecobuild blame の結果：1行ごとに「<SHA> (<人> <日付> <行番号>) <行>」）"] = None,
    selected: Annotated[str | None, "選んでいるコミット（短い SHA）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "空のときの文"] = "まだコミットしていないファイルには、注釈履歴がありません。",
) -> None: ...


def on_selected(commit: Annotated[str, "選んだコミット（短い SHA）"]) -> None:
    if not commit:
        raise ValueError("コミットが要ります")


def on_opened(commit: Annotated[str, "変更を見るコミット（短い SHA）"]) -> None:
    if not commit:
        raise ValueError("コミットが要ります")
