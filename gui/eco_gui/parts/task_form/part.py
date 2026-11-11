"""タスクの入力の窓のうち、欄を読んだ情報から組むもの：新しいタスク・作業を開始・編集・担当者を追加。

担当者や親タスクの候補・作成元の既定・タスクブランチの名前は、読んだタスク・ブランチ・アカウントから組む（見せ方）。
ここでするのは、欄を組むことだけ。描くのは、共通の部品 form と同じ所（gui/eco_gui/lib.js の form）。
入れた値を出すだけで、何が起きるかは、つないだ ecobuild のコマンドが決める（入れていない欄は出さない）。
候補（担当者・作成元のブランチ）は、届くのを待たずに窓を出し、届いたら足す（待つ間は、欄の下に「候補を読み込んでいます…」）。
"""
from typing import Annotated, Literal


def part(
    kind: Annotated[Literal["new", "start", "edit", "assign"], "どの入力の窓か"],
    issue: Annotated[int, "タスクの番号（新しいタスク・まとめて片付けるときは 0）"] = 0,
    text: Annotated[str, "窓へ渡された文字（新しいタスク：親タスクの番号）"] = "",
    status: Annotated[dict | None, "タスクの状態（task status の結果。タスクの窓で使う）"] = None,
    tasks: Annotated[list[dict], "タスク（担当者の候補・親タスクの候補にする）"] = [],
    sprints: Annotated[list[dict], "スプリント（{name, start, end}）"] = [],
    milestones: Annotated[list[dict], "マイルストーン（{title, due}）"] = [],
    branches: Annotated[list[dict], "ブランチ（branch list の行。作成元の候補にする）"] = [],
    accounts: Annotated[list[dict], "この PC でログインしているアカウント（account list の行）"] = [],
    account: Annotated[dict, "自分のアカウント（account show の結果：login・default_base）"] = {},
    members: Annotated[list[dict], "GitHub のメンバー（module members の行：login。担当者の候補に足す）"] = [],
    loading: Annotated[bool, "読み込み中（候補がまだ届いていない）"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
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


def on_cancel() -> None:
    pass
