"""タスクの一覧。番号・題名とフラグ・状態・優先度・期限・見積もり・スプリント・担当を表にする。列の見出しで並べ替え、行を選べる（右クリックでメニュー）。"""
from typing import Annotated, Any

from eco_gui.outputs import (  # タスクを描く部品で同じ出力
    task_selected as on_selected, task_dialog as on_dialog, task_edit as on_edit, task_close as on_close,
    task_remove as on_remove, task_reopen as on_reopen, task_workspace as on_workspace,
)


def part(
    tasks: Annotated[list[dict], "タスク（task list の行）"] = [],
    sprints: Annotated[list[dict], "スプリント（{name, start, end}。並べ替えと、今のスプリントの色に使う）"] = [],
    me: Annotated[str, "自分のアカウント"] = "",
    filter: Annotated[dict | None, "絞り込み（task-bar が出した値。なければ start）"] = None,
    start: Annotated[dict, "開いたときの絞り込み"] = {},
    selected: Annotated[Any, "選んでいるタスクの番号（文字でも数でも）"] = None,
    filtered: Annotated[bool, "絞り込みを当てる（当てなければ、渡したタスクを全部出す）"] = True,
    assignee: Annotated[bool, "担当の列を出す"] = True,
    foot: Annotated[bool, "下に「完了したタスクブランチを片付ける…」を出す"] = False,
    empty_text: Annotated[str, "タスクが1つもないときの文"] = "タスクはまだありません。「＋ 新しいタスク」で作れます。",
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...
