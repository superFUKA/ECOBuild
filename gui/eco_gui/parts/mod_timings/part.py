"""パイプラインのタイミングの表。操作（コミット・Push・提出・取り込み・同期・タスクの開始）ごとに、前（失敗したら止める）・後（知らせるだけ）に走らせるもの。

モジュールで共有している当て方は緑の印、この PC だけで足したものは「（このPCだけ）」の印。行の「変える…」「このPCで足す…」を押すと、
そのタイミングと今の当て方を添えて出す。
"""
from typing import Annotated


def part(
    data: Annotated[dict, "パイプラインと当て方（pipeline list：pipelines・triggers・local）"] = {},
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_changed(
    timing: Annotated[str, "タイミング（before-commit 等）"],
    local: Annotated[bool, "この PC だけで足す"],
    names: Annotated[str, "今、当てているパイプライン（カンマ区切り）"] = "",
    label: Annotated[str, "タイミングの呼び名（コミットの前 等）"] = "",
) -> None:
    if not timing:
        raise ValueError("タイミングが空です")
