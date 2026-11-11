"""モジュールの README を見せる。Markdown（.md）は、見出し・段落・リスト・引用・コード・リンク・太字・区切りの線を描く。ほかは文字のまま。"""
from typing import Annotated


def part(
    readme: Annotated[dict | None, "README（module readme：path・text・truncated。なければ null）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_reload() -> None: ...
