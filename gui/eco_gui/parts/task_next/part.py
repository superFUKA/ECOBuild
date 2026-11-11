"""次にやるタスク。順位の番号・理由の印・優先度・期限・見積もり・スプリント・担当を並べる（順番と理由は ecobuild が決める）。
期限切れ・期限が近いタスクは、あるときだけカードで出す。担当者を「自分」に絞ると、自分の担当だけの並び（mine）を出す。"""
from typing import Annotated

from eco_gui.outputs import (  # タスクを描く部品で同じ出力
    task_selected as on_selected, task_dialog as on_dialog, task_edit as on_edit, task_close as on_close,
    task_remove as on_remove, task_reopen as on_reopen, task_workspace as on_workspace,
)


def part(
    next: Annotated[list[dict], "次にやるタスク（task next の結果：{task, reasons}）"] = [],
    mine: Annotated[list[dict], "自分の担当の、次にやるタスク（task next --mine の結果）"] = [],
    overdue: Annotated[dict, "期限（task overdue の結果：{overdue, soon}）"] = {},
    sprints: Annotated[list[dict], "スプリント（{name, start, end}）"] = [],
    me: Annotated[str, "自分のアカウント"] = "",
    filter: Annotated[dict | None, "絞り込み（task-bar が出した値。なければ start）"] = None,
    start: Annotated[dict, "開いたときの絞り込み"] = {},
    selected: Annotated[str | None, "選んでいるタスクの番号"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...
