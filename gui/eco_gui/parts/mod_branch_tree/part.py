"""共有ブランチの木。名前のフォルダー（feature/…）で入れ子にし、届いている提出の件数と、どこにあるかの印を付ける。

タスクブランチは出さない。フォルダーの開閉は、この PC に覚える。↑↓ で行を移り、→ で開き、← で閉じる。
選んでいなければ、既定のブランチを選んでいるものとして見せる。
"""
from typing import Annotated


def part(
    branches: Annotated[list[dict], "ブランチ（branch list の行）"] = [],
    submissions: Annotated[list[dict], "出ている提出のタスク（task list --submitted の行。件数に使う）"] = [],
    default_base: Annotated[str, "既定のブランチ（タスクブランチの作成元）"] = "",
    selected: Annotated[str | None, "選んでいるブランチ"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_selected(name: Annotated[str, "選んだブランチ"]) -> None:
    if not name:
        raise ValueError("ブランチの名前が空です")


def on_reload() -> None: ...
