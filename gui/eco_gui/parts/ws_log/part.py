"""ログ（コミットの一覧）。短い SHA・件名・「取り込み PR #N・タスク #M」「反映 タスク #M」の印・作成者と日時。

絞り込み（件名・作成者・SHA・#タスク）、↑↓ で選ぶ、「さらに読み込む」。ブランチの一覧（branches）を渡すと、どのブランチのログを見るかを選ぶ欄を出す。選んだコミットは selected、
ダブルクリック（Enter）と右クリックのメニューは action で出す。mode が push なら、まだ送っていないコミットのメニューにする。"""
from typing import Annotated, Literal


def part(
    commits: Annotated[list[dict], "コミット（ecobuild log：sha・subject・author・date・pull_request・issue）。新しい順"] = [],
    selected: Annotated[str | None, "選んでいるコミットの SHA"] = None,
    count: Annotated[int | None, "読んだ数（これ以上あれば「さらに読み込む」を出す）"] = None,
    branches: Annotated[list[dict] | None, "選べるブランチ（ecobuild branch list：name）。あれば、ブランチを選ぶ欄を出す"] = None,
    branch: Annotated[str | None, "ログを見ているブランチ（空なら、今のブランチ）"] = "",
    mode: Annotated[Literal["log", "push", "plain"], "メニューの種類（log：戻す操作／push：取り消す・捨てる／plain：見るだけ）"] = "log",
    search: Annotated[bool, "絞り込みの欄を出す"] = True,
    short: Annotated[bool, "中身の高さに合わせる（パネルの中の短い一覧）"] = False,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "空のときの文"] = "ログはありません。",
) -> None: ...


def on_selected(sha: Annotated[str, "選んだコミットの SHA"]) -> None:
    if not sha:
        raise ValueError("コミットが要ります")


def on_action(
    name: Annotated[str, "操作の名前（show・restore・reset・undo・drop）"],
    sha: Annotated[str, "相手のコミットの SHA"],
    before: Annotated[str, "その1つ前のコミット（<SHA>~1。undo・drop で戻る先）"] = "",
) -> None:
    if not name or not sha:
        raise ValueError("操作の名前とコミットが要ります")


def on_branch(name: Annotated[str, "ログを見るブランチ（空なら、今のブランチ）"] = "") -> None: ...


def on_more(count: Annotated[int, "次に読む数"]) -> None:
    if count < 1:
        raise ValueError("数が違います")
