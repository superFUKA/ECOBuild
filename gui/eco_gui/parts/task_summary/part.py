"""タスク管理の概要。押せる数のタイル、段階のバー、今のスプリント、自分の次のタスク、期限、マイルストーン、担当者ごとの量、提出、最近完了したタスク。

数は ecobuild の結果のまま（sprint status・task workload・milestone status・task next・task overdue・task list）。押すと、その表示へ（go）。
"""
from typing import Annotated, Any

from eco_gui.outputs import (  # タスクを描く部品で同じ出力
    task_selected as on_selected, task_dialog as on_dialog, task_edit as on_edit, task_close as on_close,
    task_remove as on_remove, task_reopen as on_reopen, task_workspace as on_workspace,
)


def part(
    tasks: Annotated[list[dict], "タスク（task list --all の行）"] = [],
    sprints: Annotated[list[dict], "スプリント（{name, start, end}）"] = [],
    sprint: Annotated[dict | None, "今のスプリントの状態（sprint status の結果）"] = None,
    workload: Annotated[list[dict], "担当者ごとの量（task workload の結果）"] = [],
    milestones: Annotated[list[dict], "マイルストーンの進み具合（milestone status の結果）"] = [],
    next: Annotated[list[dict], "自分の次のタスク（task next --mine の結果）"] = [],
    overdue: Annotated[dict, "期限（task overdue の結果：{overdue, soon}）"] = {},
    reviews: Annotated[list[dict], "見るように頼まれた提出（task list --to-review の行）"] = [],
    me: Annotated[str, "自分のアカウント"] = "",
    selected: Annotated[Any, "選んでいるタスクの番号（文字でも数でも）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_go(
    screen: Annotated[str, "切り替える表示（画面の名前：tasks・board・task-next・task-sprint）"],
    filter: Annotated[dict, "その表示に付ける絞り込み（{assignee（- は担当なし）, milestone}）"] = {},
) -> None:
    if screen not in ("tasks", "board", "task-next", "task-sprint", "schedule"):
        raise ValueError("切り替えられるのは、タスク管理の表示だけです")
