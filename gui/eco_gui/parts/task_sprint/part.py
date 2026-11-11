"""スプリントの進み具合。スプリントの選択（期間・今の印）、段階ごとの件数、数のタイル（完了／全体・見積もりの残り・合計・見積もりなし）、
進み具合のバー、見積もりのないタスク・前のスプリントからの持ち越し。数は sprint status の結果のまま。"""
from typing import Annotated

from eco_gui.outputs import (  # タスクを描く部品で同じ出力
    task_selected as on_selected, task_dialog as on_dialog, task_edit as on_edit, task_close as on_close,
    task_remove as on_remove, task_reopen as on_reopen, task_workspace as on_workspace,
)


def part(
    sprints: Annotated[list[dict], "スプリント（{name, start, end}）"] = [],
    status: Annotated[dict | None, "スプリントの状態（sprint status の結果）"] = None,
    tasks: Annotated[list[dict], "タスク（task list の行。持ち越し・見積もりなしの番号に、題名を添える）"] = [],
    me: Annotated[str, "自分のアカウント"] = "",
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_chosen(name: Annotated[str, "選んだスプリントの名前"]) -> None:
    if not name:
        raise ValueError("スプリントの名前が要ります")
