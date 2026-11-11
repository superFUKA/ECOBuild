"""作業空間の帯：今の状況の知らせと、そこでできる操作のボタン。

種類（kind）ごとに、状態（ecobuild status）から文を作る。当てはまらない状況では何も出さない。
衝突で止まっている（続ける・やめる）／提出の確認中／タスクブランチではない／アーカイブ済み／完了した・上流が消えた／
最新を取り込んでいない／タスクブランチ以外に変更が残っている／仕様が古い。"""
from typing import Annotated, Literal


def part(
    kind: Annotated[Literal["conflict", "review", "notask", "archived", "gone", "behind", "left", "format", "unreadable"], "帯の種類"],
    status: Annotated[dict, "状態（ecobuild status）"] = {},
    remote: Annotated[dict, "GitHub の最新を確かめた状態（ecobuild status --fetch：base_behind・base_conflicts・archived）"] = {},
    error: Annotated[str, "状態を読めなかった理由（kind が unreadable のとき出す）"] = "",
) -> None: ...


def on_action(
    name: Annotated[str, "押したボタン（resolve・continue・abort・approve・reject・review_done・tasks・unarchive・prune・sync・discard_left・upgrade）"],
    paths: Annotated[list[str], "discard_left：捨てる変更（残っている変更の全部）"] = [],
) -> None:
    if not name:
        raise ValueError("操作の名前が要ります")
