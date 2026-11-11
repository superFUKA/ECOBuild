"""作業空間の作業のタブ（コミット・Push・提出・ログ）。タブに件数の印を出す（変更・まだ送っていないコミット・提出）。

出すタブは、今いる場所で決まる：タスクブランチと提出の確認中はコミット・（Push）・提出・ログ、ほかのブランチはログだけ。
最後に見ていたタブは、この PC に覚える。選んだタブ（開いたときは、覚えていたタブ）を selected で出す。"""
from typing import Annotated


def part(
    status: Annotated[dict, "状態（ecobuild status）"] = {},
    selected: Annotated[str | None, "今のタブ（commit・push・submit・log）"] = None,
) -> None: ...


def on_selected(tab: Annotated[str, "選んだタブ（commit・push・submit・log）"]) -> None:
    if tab not in ("commit", "push", "submit", "log"):
        raise ValueError("タブの名前が違います")
