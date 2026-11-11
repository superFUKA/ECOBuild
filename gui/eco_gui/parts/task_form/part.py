"""タスクの入力の窓の中身。新しいタスク・作業を開始・編集・完了にする・取り込む・作業を捨てる・片付ける・担当者を追加・ラベル・承認・差し戻し。

欄を描き、入れた値を出すだけ。何が起きるかは、つないだ ecobuild のコマンドが決める（入れていない欄は出さない）。
"""
from typing import Annotated, Literal


def part(
    kind: Annotated[Literal["new", "start", "edit", "complete", "finish", "drop", "prune", "clean", "assign", "label", "approve", "reject"], "どの入力の窓か"],
    issue: Annotated[int, "タスクの番号（新しいタスク・まとめて片付けるときは 0）"] = 0,
    text: Annotated[str, "窓へ渡された文字（新しいタスク：親タスクの番号）"] = "",
    status: Annotated[dict | None, "タスクの状態（task status の結果。タスクの窓で使う）"] = None,
    tasks: Annotated[list[dict], "タスク（担当者の候補・親タスクの候補にする）"] = [],
    sprints: Annotated[list[dict], "スプリント（{name, start, end}）"] = [],
    milestones: Annotated[list[dict], "マイルストーン（{title, due}）"] = [],
    branches: Annotated[list[dict], "ブランチ（branch list の行。作成元の候補にする）"] = [],
    accounts: Annotated[list[dict], "この PC でログインしているアカウント（account list の行）"] = [],
    account: Annotated[dict, "自分のアカウント（account show の結果：login・default_base）"] = {},
) -> None: ...


def _number(id: str) -> None:
    if not id or id == "0":
        raise ValueError("タスクの番号が要ります")


def on_new(
    title: Annotated[str, "題名"], body: Annotated[str, "本文"] = "", stage: Annotated[str, "段階（planned。未着手なら空）"] = "",
    assignee: Annotated[str, "担当者（カンマ区切り）"] = "", priority: Annotated[str, "優先度"] = "", estimate: Annotated[str, "見積もり"] = "",
    sprint: Annotated[str, "スプリント"] = "", planned_start: Annotated[str, "開始予定日"] = "", planned_end: Annotated[str, "終了予定日"] = "",
    due: Annotated[str, "期限"] = "", label: Annotated[str, "ラベル（カンマ区切り）"] = "", milestone: Annotated[str, "マイルストーン"] = "",
    parent: Annotated[str, "親タスクの番号"] = "", blocked_by: Annotated[str, "先に終わるべきタスクの番号（カンマ区切り）"] = "",
    start: Annotated[bool, "作ったら、作業を開始する"] = False, name: Annotated[str, "タスクブランチの名前"] = "",
) -> None:
    if not title.strip():
        raise ValueError("題名を入力してください")
    if start and not name.strip():
        raise ValueError("タスクブランチの名前を入力してください")


def on_start(
    id: Annotated[str, "タスクの番号"], name: Annotated[str, "タスクブランチの名前"] = "", base: Annotated[str, "作成元のブランチ（既定から変えたときだけ）"] = "",
    account: Annotated[str, "作業空間で使うアカウント"] = "", no_branch: Annotated[bool, "タスクブランチを作らない"] = False,
    ignore_blocked: Annotated[bool, "先に終わるべきタスクが開いていても始める"] = False, take_over: Annotated[bool, "ほかの人から引き継ぐ"] = False,
) -> None:
    _number(id)


def on_edit(
    id: Annotated[str, "タスクの番号"], title: Annotated[str, "新しい題名"] = "", body: Annotated[str, "新しい本文"] = "",
    parent: Annotated[str, "親タスクの番号"] = "", clear_parent: Annotated[bool, "親タスクから外す"] = False,
    add_blocked_by: Annotated[str, "先に終わるべきタスクを加える"] = "", remove_blocked_by: Annotated[str, "先に終わるべきタスクから外す"] = "",
    add_assignee: Annotated[str, "加える担当者"] = "", add_label: Annotated[str, "付けるラベル"] = "",
) -> None:
    _number(id)


def on_finish(
    id: Annotated[str, "タスクの番号"], subject: Annotated[str, "取り込むコミットの件名"] = "",
    ignore_checks: Annotated[bool, "CI が失敗していても取り込む"] = False,
    complete: Annotated[bool, "タスクを完了する"] = False, partial: Annotated[bool, "タスクを閉じずに続ける"] = False,
) -> None:
    _number(id)


def on_drop(id: Annotated[str, "タスクの番号"], close: Annotated[bool, "タスクも削除する"] = False) -> None:
    _number(id)


def on_prune(id: Annotated[str, "タスクの番号"]) -> None:
    _number(id)


def on_clean() -> None:
    pass


def on_approve(id: Annotated[str, "タスクの番号"], message: Annotated[str, "コメント"] = "") -> None:
    _number(id)


def on_reject(id: Annotated[str, "タスクの番号"], message: Annotated[str, "直してほしいこと"]) -> None:
    _number(id)
    if not message.strip():
        raise ValueError("直してほしいことを書いてください")


def on_cancel() -> None:
    pass
