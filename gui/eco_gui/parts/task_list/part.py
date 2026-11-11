"""タスクの一覧。番号・題名とフラグ・状態・優先度・期限・見積もり・スプリント・担当を表にする。列の見出しで並べ替え、行を選べる（右クリックでメニュー）。"""
from typing import Annotated


def part(
    tasks: Annotated[list[dict], "タスク（task list の行）"] = [],
    sprints: Annotated[list[dict], "スプリント（{name, start, end}。並べ替えと、今のスプリントの色に使う）"] = [],
    me: Annotated[str, "自分のアカウント"] = "",
    filter: Annotated[dict | None, "絞り込み（task-bar が出した値。なければ start）"] = None,
    start: Annotated[dict, "開いたときの絞り込み"] = {},
    selected: Annotated[str | None, "選んでいるタスクの番号"] = None,
    filtered: Annotated[bool, "絞り込みを当てる（当てなければ、渡したタスクを全部出す）"] = True,
    assignee: Annotated[bool, "担当の列を出す"] = True,
    foot: Annotated[bool, "下に「完了したタスクブランチを片付ける…」を出す"] = False,
    empty_text: Annotated[str, "タスクが1つもないときの文"] = "タスクはまだありません。「＋ 新しいタスク」で作れます。",
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


# <<タスクの出力（タスクを描く部品で同じもの）
def on_selected(id: Annotated[str, "選んだタスクの番号"]) -> None:
    if not id:
        raise ValueError("タスクの番号が要ります")


def on_dialog(
    screen: Annotated[str, "開く入力の窓（画面の名前：task-start・task-edit・task-complete・task-drop・task-prune・task-assign・task-new・task-person ほか）"],
    id: Annotated[str, "タスクの番号（タスクによらない窓は 0）"] = "0",
    text: Annotated[str, "窓へ渡す文字（人の画面：アカウント、新しいタスク：親タスクの番号）"] = "",
) -> None:
    if not screen.startswith("task-"):
        raise ValueError("開けるのは、タスクの入力の窓だけです")


def on_edit(
    id: Annotated[str, "タスクの番号"],
    priority: Annotated[str, "優先度"] = "", sprint: Annotated[str, "スプリント"] = "", stage: Annotated[str, "段階（planned・todo）"] = "",
    estimate: Annotated[str, "見積もり"] = "", due: Annotated[str, "期限"] = "",
    planned_start: Annotated[str, "開始予定"] = "", planned_end: Annotated[str, "終了予定"] = "",
    milestone: Annotated[str, "マイルストーン"] = "", clear_milestone: Annotated[bool, "マイルストーンから外す"] = False,
    add_assignee: Annotated[str, "加える担当者"] = "", remove_assignee: Annotated[str, "外す担当者"] = "",
    add_label: Annotated[str, "付けるラベル"] = "", remove_label: Annotated[str, "外すラベル"] = "",
    clear: Annotated[str, "消す計画の値"] = "",
) -> None:
    if not id:
        raise ValueError("タスクの番号が要ります")


def on_close(id: Annotated[str, "完了にするタスクの番号（タスクブランチのないもの）"]) -> None:
    if not id:
        raise ValueError("タスクの番号が要ります")


def on_remove(id: Annotated[str, "削除するタスクの番号（あとで元に戻せる）"]) -> None:
    if not id:
        raise ValueError("タスクの番号が要ります")


def on_reopen(id: Annotated[str, "開き直すタスクの番号"]) -> None:
    if not id:
        raise ValueError("タスクの番号が要ります")


def on_workspace(path: Annotated[str, "開く作業空間のフォルダー"]) -> None:
    if not path:
        raise ValueError("作業空間のフォルダーが要ります")
# タスクの出力>>
