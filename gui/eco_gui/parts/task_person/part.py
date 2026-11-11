"""人の画面の上の部分。大きな丸と名前（自分の印）、担当・作業中・残りの見積もり・期限切れ・提出中の数、作業中・提出・見るように頼まれた提出の並び。"""
from typing import Annotated

from eco_gui.outputs import (  # タスクを描く部品で同じ出力
    task_selected as on_selected, task_dialog as on_dialog, task_edit as on_edit, task_close as on_close,
    task_remove as on_remove, task_reopen as on_reopen, task_workspace as on_workspace,
)


def part(
    who: Annotated[str, "アカウント"],
    tasks: Annotated[list[dict], "タスク（task list の行）"] = [],
    workload: Annotated[list[dict], "担当者ごとの量（task workload の結果）"] = [],
    submitted: Annotated[list[dict], "提出中のタスク（task list --submitted の行）"] = [],
    reviews: Annotated[list[dict], "見るように頼まれた提出（task list --to-review の行。自分の画面のときだけ出す）"] = [],
    me: Annotated[str, "自分のアカウント"] = "",
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_closed() -> None:
    pass
