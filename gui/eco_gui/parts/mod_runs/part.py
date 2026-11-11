"""CI の実行の表。結果の印（色）・番号・ブランチ・きっかけ・日時と、行のボタン（ログ・再実行・GitHub で開く）。

上に、ブランチで絞る欄・「GitHub で見る」・「▶ 手動で実行」。行の右クリックで、同じ操作と「このブランチの実行だけを表示」。
ブランチを選んでいるあいだは、そのブランチの実行（branch_rows）を見せる。
"""
from typing import Annotated


def part(
    rows: Annotated[list[dict], "すべてのブランチの実行（ci status --all）"] = [],
    branch_rows: Annotated[list[dict], "選んだブランチの実行（ci status --branch）"] = [],
    branch: Annotated[str | None, "絞っているブランチ（なければ、すべて）"] = None,
    branches: Annotated[list[dict], "ブランチ（branch list の行。GitHub にあるものを選べる）"] = [],
    url: Annotated[str, "GitHub のリポジトリの URL（「GitHub で見る」の先）"] = "",
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_branch(name: Annotated[str, "絞るブランチ（空なら、すべて）"]) -> None: ...


def on_action(
    action: Annotated[str, "押した操作：logs（失敗した手順のログ）・rerun（もう一度実行）・rerun_failed（失敗したジョブだけ実行）"],
    run: Annotated[int, "実行の番号"],
) -> None:
    if action not in ("logs", "rerun", "rerun_failed"):
        raise ValueError(f"知らない操作です：{action}")


def on_dispatch(branch: Annotated[str, "絞っているブランチ（手動で実行の初めの値。なければ空）"] = "") -> None: ...


def on_reload() -> None: ...
