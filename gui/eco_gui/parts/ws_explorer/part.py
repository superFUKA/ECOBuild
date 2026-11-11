"""作業空間のエクスプローラー。ファイルの木に、変更の状態を色と印で出す（+ 新しい・• 変更・✓ ステージ済み・衝突は赤・削除は取り消し線）。

クリック（Ctrl・Shift でいくつも）で選び、右クリックのメニュー・F2（その場で名前を変える）・Delete で操作を出す。
することは出力（action）で出すだけ。実行は画面のつなぎが ecobuild のコマンドでする。"""
from typing import Annotated


def part(
    files: Annotated[list[str], "ファイルのパス（/ で区切る）"] = [],
    missing: Annotated[list[str] | None, "今はフォルダーにないファイル（消した・動かした）。取り消し線で出す"] = None,
    status: Annotated[dict, "状態（ecobuild status：staged・unstaged・untracked・conflicted の並び）"] = {},
    projects: Annotated[list | None, "サブプロジェクト（名前か {name, kind, directory}）。あれば、そのフォルダーだけを出し、◆ と種類を付ける"] = None,
    selected: Annotated[str | None, "選んでいるファイル（変更の一覧と合わせる）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "空のときの文"] = "ファイルはありません。",
) -> None: ...


def on_selected(path: Annotated[str, "選んだファイル"]) -> None:
    if not path:
        raise ValueError("パスが空です")


def on_action(
    name: Annotated[str, "操作の名前（rename・remove・restore・ignore・diff・log・blame・new_file・move・run_test・make_test・"
                         "resolve・take_current・take_incoming・commit・reload）"],
    path: Annotated[str, "相手のファイル・フォルダー（1つのとき）"] = "",
    paths: Annotated[list[str], "相手のファイル・フォルダー（いくつものとき。1つのときも入る）"] = [],
    to: Annotated[str, "rename：新しいパス"] = "",
) -> None:
    if not name:
        raise ValueError("操作の名前が要ります")
    if name == "rename" and (not path or not to):
        raise ValueError("名前を変える相手と、新しい名前が要ります")
