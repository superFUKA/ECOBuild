"""届いている提出の一覧。届け先のブランチごとに、タスクの提出と、ブランチ同士の提出（「ブランチ」の印）を並べる。

見出しに件数。行に、提出の状態の文と担当（自分なら「（自分）」）。見るように頼まれている提出には印を付ける。
そのブランチへの提出を処理できない人には、だれが処理できるかを出す（account show の答え）。行を選ぶと selected。
"""
from typing import Annotated, Literal


def part(
    tasks: Annotated[list[dict], "提出中のタスク（task list --submitted の結果）"],
    branches: Annotated[list[dict], "ブランチ（branch list の結果。ブランチ同士の提出を拾う）"] = [],
    to_review: Annotated[list[dict], "見るように頼まれている提出（task list --to-review の結果）"] = [],
    access: Annotated[dict | None, "アカウントと、提出を処理できるか（account show の結果）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_selected(kind: Annotated[Literal["task", "branch"], "タスクの提出か、ブランチ同士の提出か"],
                id: Annotated[str, "タスクの番号・ブランチの名前"]) -> None:
    if not id:
        raise ValueError("どの提出かが要ります")
