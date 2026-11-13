"""モジュールの README を見せる。Markdown（.md）は、見出し・段落・リスト・引用・コード・リンク・太字・区切りの線を描く。ほかは文字のまま。

題の横の「✎ 編集」で、README を既定のアプリで開く（edit。変えたら、タスクブランチでコミット）。
"""
from typing import Annotated


def part(
    readme: Annotated[dict | None, "README（module readme：path・text・truncated。なければ null）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_reload() -> None: ...


def on_edit(path: Annotated[str, "README のファイル（モジュールからの相対）"]) -> None:
    if not path:
        raise ValueError("ファイルが要ります")
