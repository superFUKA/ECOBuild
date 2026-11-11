"""コミットの一覧。上でブランチを選ぶ。行は、日時・だれが・SHA（短く）・何を、と提出（PR）・タスク（Issue）の印。行を選ぶと、そのコミットを出す。"""
from typing import Annotated


def part(
    rows: Annotated[list[dict], "コミット（log の行：sha・subject・author・date・pull_request・issue）"] = [],
    branches: Annotated[list[dict], "ブランチ（branch list の行。共有ブランチを選べる）"] = [],
    branch: Annotated[str | None, "見ているブランチ（なければ、今いるブランチ）"] = None,
    selected: Annotated[str | None, "選んでいるコミットの SHA"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_selected(sha: Annotated[str, "選んだコミットの SHA"]) -> None:
    if not sha:
        raise ValueError("SHA が空です")


def on_branch(name: Annotated[str, "見るブランチ（空なら、今いるブランチ）"]) -> None: ...


def on_reload() -> None: ...
