"""変更のあるファイルを、フォルダーの木（サブプロジェクトがあれば、そのまとまり）で並べ、チェックで選ぶ。

種類は右に色で出す（衝突＝赤・ステージ済み＝青・変更＝橙・追加＝緑・削除＝薄い赤）。「改行のみ」「管理外」の印も出す。
まとまり（全部・サブプロジェクト・フォルダー）のチェックで、中をまとめて選べる。見出しの行のボタンと右クリックのメニューは、出力（action）で出す。"""
from typing import Annotated


def part(
    status: Annotated[dict, "状態（ecobuild status：staged・unstaged・untracked・conflicted・eol_only・excluded・merging・branch）"] = {},
    checked: Annotated[list[str], "選んでいるファイル"] = [],
    selected: Annotated[str | None, "名前を押したファイル（強調する）"] = None,
    missing: Annotated[list[str] | None, "今はフォルダーにないファイル（「削除」と出す）"] = None,
    projects: Annotated[list | None, "サブプロジェクト（名前か {name, kind, directory}）。あれば、そのまとまりで分ける"] = None,
    stashes: Annotated[list[str], "退避した変更（ecobuild stash list）。「退避」のメニューに数と理由を出す"] = [],
    tools: Annotated[bool, "見出しの行（全部選ぶ・件数・差分・元に戻す・退避）を出す"] = False,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "変更がないときの文"] = "変更はありません。",
    none_when_empty: Annotated[bool, "チェックが1つもないとき、changed で null を出す（まだ選んでいない、にする）"] = False,
) -> None: ...


def on_changed(paths: Annotated[list[str] | None, "チェックを付けたファイル（none_when_empty なら、1つもないとき null）"]) -> None: ...


def on_selected(path: Annotated[str, "名前を押したファイル（差分を見る）"]) -> None:
    if not path:
        raise ValueError("パスが空です")


def on_action(
    name: Annotated[str, "操作の名前（stage・unstage・discard・diff・diff_dialog・restore・ignore・log・blame・"
                         "stash・stash_pop・stash_list・stash_drop）"],
    path: Annotated[str, "相手のファイル（1つのとき）"] = "",
    paths: Annotated[list[str], "相手のファイル（チェックしたもの。1つのときも入る）"] = [],
) -> None:
    if not name:
        raise ValueError("操作の名前が要ります")
