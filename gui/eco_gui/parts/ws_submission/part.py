"""作業空間の「提出」のタブ：この作業空間のタスクの提出（前の GUI の prs.js と同じ）。

上の行に「#番号 題」と提出の状態、右にすること：タスクブランチなら「提出を取り下げる」と、作成元を処理できる人は「反映」・
ほかの人は「下書きを解除」「提出」。提出の確認中なら「判定せずに終える」「差し戻す」「承認して取り込む」。
次の行に、タスクブランチ → 作成元・担当・CI・取り込めるかと、見るボタン（差分・コメント・タスク・更新）。まだ Push していない
コミットの注意、レビューとコメントの流れ。押したボタンは action で出す（何をするかは、画面のつなぎが決める）。"""
from typing import Annotated, Literal


def part(
    status: Annotated[dict, "状態（ecobuild status：task・reviewing・reviewing_task・ahead・finished・upstream_gone）"] = {},
    task: Annotated[dict | None, "このタスクの提出（ecobuild task status：number・title・branch・base・assignees・pull_request・activity・commits・comments）"] = None,
    review: Annotated[dict | None, "提出の確認中なら、確認している提出（ecobuild task status <確認中のタスク>。形は task と同じ）"] = None,
    access: Annotated[dict | None, "アカウントと、提出を処理できるか（ecobuild account show：login・take_in・take_in_other）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_action(
    action: Annotated[Literal["diff", "comment", "task", "refresh", "submit", "ready", "apply", "withdraw", "review_done", "reject", "approve",
                              "full_log"], "押したボタン"],
    id: Annotated[str, "タスクの番号"],
) -> None:
    if not id:
        raise ValueError("どのタスクかが要ります")
