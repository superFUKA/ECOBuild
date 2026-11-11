"""タスクの詳細。番号と段階、状態に合った主ボタンと ⋯ メニュー、本文（長ければ折りたたむ）、担当者・ラベルのチップ、
その場で変えられる計画の値（優先度・見積もり・スプリント・マイルストーン・日付）、つながり、作業と提出、コメント。"""
from typing import Annotated


def part(
    status: Annotated[dict | None, "タスクの状態（task status の結果）"] = None,
    number: Annotated[str | None, "選んでいるタスクの番号（status がまだ前のタスクのあいだは、読み込み中を出す）"] = None,
    sprints: Annotated[list[dict], "スプリント（{name, start, end}）"] = [],
    milestones: Annotated[list[dict], "マイルストーン（{title}）"] = [],
    account: Annotated[dict, "自分のアカウント（account show の結果：login・admin・default_base・creators）"] = {},
    closable: Annotated[bool, "× で閉じられる（一覧の右に出しているとき）"] = True,
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
