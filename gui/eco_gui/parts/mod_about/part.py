"""「このモジュール」の欄。GitHub のリンク、公開/非公開・アーカイブ済みの印、型、タスクブランチの作成元、Project と依存先の印、場所。

作業空間が1つもないときは、下に「今は見るだけ」の帯と「タスク管理を開く」を出す。
"""
from typing import Annotated


def part(
    data: Annotated[dict, "モジュールの情報（module show）"] = {},
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_opened(page: Annotated[str, "開く先：deps（依存関係）・tasks（タスク管理）"]) -> None:
    if page not in ("deps", "tasks"):
        raise ValueError(f"知らない先です：{page}")


def on_reload() -> None: ...
