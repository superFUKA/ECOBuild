"""「完了したタスクブランチを片付ける」の窓の中身。消すタスクブランチ・一緒に消える作業空間・残すものと理由（task prune の下見）を見せて、確かめる。

何を消し、何を残すかは ecobuild が決める（下見の結果のまま出す）。消すものがなければ、「閉じる」だけを出す。
"""
from typing import Annotated


def part(
    preview: Annotated[dict | None, "下見（task prune --dry-run の結果：{removed, workspaces_removed, skipped: [{branch, reason}]}）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "下見ができなかった理由"] = "",
) -> None: ...


def on_clean() -> None:
    pass


def on_cancel() -> None:
    pass
