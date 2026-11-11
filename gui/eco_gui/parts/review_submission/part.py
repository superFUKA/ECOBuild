"""提出の詳細。1つのタスクの提出（か、ブランチ同士の提出）の状態・CI・入るコミット・やりとりと、できる操作のボタン。

処理できるか・できる人は、account show の答え（take_in）をそのまま使う。処理できない人には説明を出し、ボタンを灰色にして
理由を出す。押したボタンは action で出す（何をするかは、画面のつなぎが決める）。
"""
from typing import Annotated, Literal


def part(
    task: Annotated[dict | None, "タスクの提出（task status の結果）"] = None,
    branch: Annotated[dict | None, "ブランチ同士の提出（branch list の1行：name・submitted_to・submission）"] = None,
    branches: Annotated[list[dict], "ブランチの一覧（branch list の結果。name の行を、ブランチ同士の提出として出す）"] = [],
    name: Annotated[str, "ブランチ同士の提出を出すブランチ（branches から探す）"] = "",
    access: Annotated[dict | None, "アカウントと、提出を処理できるか（account show の結果：login・take_in・take_in_other）"] = None,
    spaces: Annotated[list[dict], "作業空間（module show の workspaces。確認中の作業空間があるかを見る）"] = [],
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_action(
    action: Annotated[Literal["diff", "comment", "task", "refresh", "review", "review_done", "reject", "approve", "withdraw", "finish",
                              "apply", "merge", "open_review"], "押したボタン"],
    id: Annotated[str, "タスクの番号（ブランチ同士の提出なら、ブランチの名前）"],
    base: Annotated[str, "取り込み先のブランチ"] = "",
    partial: Annotated[bool, "中間提出か（取り込んでもタスクを続ける）"] = False,
    workspace: Annotated[str, "確認中の作業空間（あれば）"] = "",
) -> None:
    if not id:
        raise ValueError("どの提出かが要ります")
