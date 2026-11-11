"""日程。タスクの開始予定〜終了予定を、横の帯か、月のカレンダーで見せる（期限は ◆）。帯は段階の色で、終了予定を過ぎたものは赤い枠。

横の帯では、帯をドラッグして予定を動かす・右端で終了予定を変える・予定のない行をドラッグして予定を付ける（edit を出す）。
"""
from typing import Annotated, Any

from eco_gui.outputs import (  # タスクを描く部品で同じ出力
    task_selected as on_selected, task_dialog as on_dialog, task_edit as on_edit, task_close as on_close,
    task_remove as on_remove, task_reopen as on_reopen, task_workspace as on_workspace,
)


def part(
    tasks: Annotated[list[dict], "タスク（task list の行。日付は YYYY-MM-DD）"] = [],
    sprints: Annotated[list[dict], "スプリント（{name, start, end}）"] = [],
    me: Annotated[str, "自分のアカウント"] = "",
    filter: Annotated[dict | None, "絞り込み（task-bar が出した値。なければ start）"] = None,
    start: Annotated[dict, "開いたときの絞り込み"] = {},
    selected: Annotated[Any, "選んでいるタスクの番号（文字でも数でも）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...
