"""作業空間の作業のタブ（コミット・Push・提出・ログ）。タブに件数の印を出す（変更・まだ送っていないコミット・提出）。

出すタブは、今いる場所で決まる：タスクブランチと提出の確認中はコミット・（Push）・提出、ほかのブランチはログだけ（取り込みの途中はコミットも）。
提出のタブの数は、提出に入るコミットの数。
最後に見ていたタブは、この PC に覚える。選んだタブ（開いたときは、覚えていたタブ）を selected で出す。"""
from typing import Annotated


def part(
    status: Annotated[dict, "状態（ecobuild status）"] = {},
    task: Annotated[dict | None, "今いるタスクの提出（ecobuild task status：commits）。提出のタブに、入るコミットの数を出す"] = None,
    selected: Annotated[str | None, "今のタブ（commit・push・submit・log）"] = None,
) -> None: ...


def on_selected(tab: Annotated[str, "選んだタブ（commit・push・submit・log）"]) -> None:
    if tab not in ("commit", "push", "submit", "log"):
        raise ValueError("タブの名前が違います")
