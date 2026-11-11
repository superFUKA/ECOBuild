"""タスクの詳細。番号と段階、状態に合った主ボタンと ⋯ メニュー、本文（長ければ折りたたむ）、担当者・ラベルのチップ、
その場で変えられる計画の値（優先度・見積もり・スプリント・マイルストーン・日付）、つながり、作業と提出、コメント。"""
from typing import Annotated, Any

from eco_gui.outputs import (  # タスクを描く部品で同じ出力
    task_selected as on_selected, task_dialog as on_dialog, task_edit as on_edit, task_close as on_close,
    task_remove as on_remove, task_reopen as on_reopen, task_workspace as on_workspace,
)


def part(
    status: Annotated[dict | None, "タスクの状態（task status の結果）"] = None,
    number: Annotated[Any, "選んでいるタスクの番号（文字でも数でも。status がまだ前のタスクのあいだは、読み込み中を出す）"] = None,
    sprints: Annotated[list[dict], "スプリント（{name, start, end}）"] = [],
    milestones: Annotated[list[dict], "マイルストーン（{title}）"] = [],
    me: Annotated[str, "自分のアカウント"] = "",
    can_approve: Annotated[dict, "提出を承認できるか・できない理由（{can, reason}。task approve --can の答え）"] = {},
    can_reject: Annotated[dict, "提出を差し戻せるか・できない理由（{can, reason}。task reject --can の答え）"] = {},
    can_finish: Annotated[dict, "提出を取り込めるか・できない理由（{can, reason}。task finish --can の答え）"] = {},
    closable: Annotated[bool, "× で閉じられる（一覧の右に出しているとき）"] = True,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_closed() -> None:
    pass


def on_comment(id: Annotated[str, "タスクの番号"], message: Annotated[str, "コメントの文"]) -> None:
    if not id or not message.strip():
        raise ValueError("コメントを書いてください")


def on_withdraw(id: Annotated[str, "提出を取り下げるタスクの番号"]) -> None:
    if not id:
        raise ValueError("タスクの番号が要ります")


def on_review(id: Annotated[str, "提出を手元で確かめるタスクの番号"]) -> None:
    if not id:
        raise ValueError("タスクの番号が要ります")


def on_revert(id: Annotated[str, "取り込みを取り消すタスクの番号"]) -> None:
    if not id:
        raise ValueError("タスクの番号が要ります")


def on_submission(id: Annotated[str, "提出（差分）を見るタスクの番号"]) -> None:
    if not id:
        raise ValueError("タスクの番号が要ります")
