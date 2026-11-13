"""作業空間のエクスプローラー。ファイルの木に、変更の状態を色と印で出す（+ 新しい・• 変更・✓ ステージ済み・衝突は赤・削除は取り消し線）。

クリック（Ctrl・Shift でいくつも）で選び、右クリックのメニュー・F2（その場で名前を変える）・Delete で操作を出す。ダブルクリックで開く
（open：開発の道具で）。メニューから Visual Studio・既定のアプリ・エクスプローラーでも開ける。ファイルのメニューは変更の一覧と同じ
（テストを開く・テストの対象を開く・一緒に開く・テストを作成 等）。サブプロジェクトのフォルダーには、ビルド・テスト・実行・実行の対象・
移動・削除・設定のメニュー。ドラッグで、ファイル・フォルダーを別のフォルダーへ動かす（1つは drop_move、いくつもは drop_move_into）。
新しいフォルダは、その場で名前を打って make_folder（ディスクに作る）。
作った（made）・動かした（moved）ファイルが届いたら、木で選ぶ（作ったものは開く）。済んだら revealed を出す。
することは出力（action）で出すだけ。実行は画面のつなぎが ecobuild のコマンドでする。"""
from typing import Annotated


def part(
    files: Annotated[list[str], "ファイルのパス（/ で区切る）"] = [],
    missing: Annotated[list[str] | None, "今はフォルダーにないファイル（消した・動かした）。取り消し線で出す"] = None,
    generated: Annotated[list[str] | None, "生成ファイル（道具が作り直すもの。ecobuild files の generated）。ふだんは隠し、見出しの目の印で出す（灰色の斜体）"] = None,
    status: Annotated[dict, "状態（ecobuild status：staged・unstaged・untracked・conflicted の並び）"] = {},
    folders: Annotated[list[str] | None, "中にファイルのないフォルダー（ecobuild files の folders。git は記録しない）。木に出す"] = None,
    projects: Annotated[list | None, "サブプロジェクト（名前か {name, kind, directory}）。あれば、そのフォルダーだけを出し、◆ と種類を付ける"] = None,
    selected: Annotated[str | None, "選んでいるファイル（変更の一覧と合わせる）"] = None,
    module_type: Annotated[str | None, "モジュールの型（cpp なら、見出しに SLN（ソリューションを作り直す）を出す）"] = "",
    vs_version: Annotated[str | None, "ファイルを開く Visual Studio の版（メニューの文に出す）"] = "",
    made: Annotated[list[str] | None, "作ったファイル（届いたら、最後のものを木で選び、開発の道具で開く）"] = None,
    moved: Annotated[str | None, "動かした先（届いたら、木で選ぶ）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
    empty_text: Annotated[str, "空のときの文"] = "ファイルはありません。",
) -> None: ...


def on_selected(path: Annotated[str, "選んだファイル"]) -> None:
    if not path:
        raise ValueError("パスが空です")


def on_action(
    name: Annotated[str, "操作の名前（rename・drop_move・remove・restore・ignore・diff・view_new・log・blame・new_file・move・run_test・"
                         "make_test・make_tests・make_folder・move_into・drop_move_into・resolve・take_current・take_incoming・commit・reload・sln・open・open_all・open_vs・open_default・"
                         "open_default_all・reveal・revealed・project_build・project_rebuild・project_clean・project_test・project_run・"
                         "run_target・project_move・project_remove・project_settings）"],
    path: Annotated[str, "相手のファイル・フォルダー（1つのとき）"] = "",
    paths: Annotated[list[str], "相手のファイル・フォルダー（いくつものとき。1つのときも入る）"] = [],
    to: Annotated[str, "rename・drop_move：新しいパス／drop_move_into：移動先のフォルダー（一番上なら「.」）"] = "",
    project: Annotated[str, "project_…・run_target：サブプロジェクトの名前"] = "",
) -> None:
    if not name:
        raise ValueError("操作の名前が要ります")
    if name in ("rename", "drop_move") and (not path or not to):
        raise ValueError("動かす相手と、新しい名前が要ります")
    if (name.startswith("project_") or name == "run_target") and not project:
        raise ValueError("サブプロジェクトの名前が要ります")
