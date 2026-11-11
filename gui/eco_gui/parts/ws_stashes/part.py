"""退避の一覧：このブランチで退避した変更（番号・何を・いつのブランチか）と、「戻す」「削除…」。上に「変更を退避」。

退避（stash）はモジュールの作業空間すべてで共有なので、このブランチのものと、ほかのブランチのもの（数と一覧。ここでは扱わない）を分けて見せる
（「On <ブランチ>: …」「WIP on <ブランチ>: …」の形で分ける。見せ方だけ）。番号は、ecobuild stash list の番号。
"""
from typing import Annotated


def part(
    stashes: Annotated[list[str], "退避した変更（ecobuild stash list。新しい順。並びの位置が番号）"] = [],
    status: Annotated[dict, "状態（ecobuild status：branch・staged・unstaged・untracked）"] = {},
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_action(
    name: Annotated[str, "押した操作：stash（変更を退避）・pop（戻す）・drop（削除…）"],
    index: Annotated[int, "退避の番号（pop・drop）"] = -1,
) -> None:
    if name not in ("stash", "pop", "drop"):
        raise ValueError(f"知らない操作です：{name}")
    if name != "stash" and index < 0:
        raise ValueError("退避の番号が要ります")


def on_reload() -> None: ...
