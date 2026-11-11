"""選んだ共有ブランチの詳細。見出し（名前・印・どこにあるか・作成元・作った人）、作業・仕様・保護、このブランチから作ったタスクブランチ。

選んでいなければ、既定のブランチを見せる。できるかどうかは決めない（押した操作は、ecobuild が確かめる）。
"""
from typing import Annotated


def part(
    branches: Annotated[list[dict], "ブランチ（branch list の行。タスクブランチも）"] = [],
    selected: Annotated[str | None, "選んでいるブランチ"] = None,
    default_base: Annotated[str | None, "既定のブランチ（タスクブランチの作成元）"] = None,
    creators: Annotated[dict | None, "ブランチを作った人（名前 → アカウント。account show の creators）"] = None,
    protection: Annotated[dict | None, "既定のブランチの保護（module protection。なければ null）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_action(
    action: Annotated[str, "押した操作：merge（取り込み・提出…）・delete（削除…）・protect（保護の設定…）・unprotect（保護を外す）・task（タスクを開く）"],
    name: Annotated[str, "ブランチの名前"],
    task: Annotated[int, "タスクの番号（task のとき）"] = 0,
) -> None:
    if action not in ("merge", "delete", "protect", "unprotect", "task"):
        raise ValueError(f"知らない操作です：{action}")


def on_reload() -> None: ...
