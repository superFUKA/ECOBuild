"""ボード。タスクを段階ごとの列（計画中・未着手・作業中・レビュー待ち・完了、削除済み）にカードで並べる。カードを選べ、別の列へドラッグできる（右クリックでメニュー）。

完了の列は、最近完了した 15 件（recent）。「完了したタスクも表示」のときは、全部を出す。
"""
from typing import Annotated, Any

from eco_gui.outputs import (  # タスクを描く部品で同じ出力
    task_selected as on_selected, task_dialog as on_dialog, task_edit as on_edit, task_close as on_close,
    task_remove as on_remove, task_reopen as on_reopen, task_workspace as on_workspace,
)


def part(
    tasks: Annotated[list[dict], "タスク（task list の行）"] = [],
    recent: Annotated[list[dict], "閉じたものも入ったタスク（task list --all の行。完了の列に、最近のものを出す）"] = [],
    sprints: Annotated[list[dict], "スプリント（{name, start, end}）"] = [],
    me: Annotated[str, "自分のアカウント"] = "",
    filter: Annotated[dict | None, "絞り込み（task-bar が出した値。なければ start）"] = None,
    start: Annotated[dict, "開いたときの絞り込み"] = {},
    selected: Annotated[Any, "選んでいるタスクの番号（文字でも数でも）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...
