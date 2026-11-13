"""届いている提出の一覧。届け先のブランチごとに、タスクの提出と、ブランチ同士の提出（「ブランチ」の印）を並べる。

見出しに件数。行に、提出の状態の文と担当（自分なら「（自分）」）。見るように頼まれている提出には印を付ける。
そのブランチへの提出を処理できない人には、だれが処理できるかを出す（account show の答え）。
行を選ぶと selected（何も選んでいなければ、先頭の行を選ぶ。↑↓ で選び直す）。行の右クリックで、詳細のボタンと同じ操作（action）と
「GitHubで開く」。
"""
from typing import Annotated, Literal


def part(
    tasks: Annotated[list[dict], "提出中のタスク（task list --submitted の結果）"],
    branches: Annotated[list[dict], "ブランチ（branch list の結果。ブランチ同士の提出を拾う）"] = [],
    to_review: Annotated[list[dict], "見るように頼まれている提出（task list --to-review の結果）"] = [],
    access: Annotated[dict | None, "アカウントと、提出を処理できるか（account show の結果）"] = None,
    selected_task: Annotated[str | None, "選んでいるタスクの提出（タスクの番号）"] = None,
    selected_branch: Annotated[str | None, "選んでいるブランチ同士の提出（ブランチの名前）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_selected(kind: Annotated[Literal["task", "branch"], "タスクの提出か、ブランチ同士の提出か"],
                id: Annotated[str, "タスクの番号・ブランチの名前"],
                task: Annotated[str, "タスクの番号（タスクの提出のとき。ほかは空）"] = "",
                branch: Annotated[str, "ブランチの名前（ブランチ同士の提出のとき。ほかは空）"] = "") -> None:
    if not id:
        raise ValueError("どの提出かが要ります")


def on_action(
    action: Annotated[Literal["diff", "comment", "task", "review", "reject", "approve", "withdraw", "finish", "merge"], "選んだ操作（詳細のボタンと同じ）"],
    id: Annotated[str, "タスクの番号（ブランチ同士の提出なら、ブランチの名前）"],
    base: Annotated[str, "取り込み先のブランチ"] = "",
    partial: Annotated[bool, "中間提出か"] = False,
    workspace: Annotated[str, "確認中の作業空間（使わない）"] = "",
) -> None:
    if not id:
        raise ValueError("どの提出かが要ります")
