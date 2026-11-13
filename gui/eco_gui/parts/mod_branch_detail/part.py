"""選んだ共有ブランチの詳細。見出し（名前・印・どこにあるか・作成元・作った人）、作業・提出を処理できる人・仕様・保護、
このブランチから作ったタスクブランチ（それぞれ「タスクブランチを開く」）。

選んでいなければ、既定のブランチを見せる。管理者でない人の「削除…」は、account show の答え（admin）のとおり灰色と理由にする
（表示だけ。押した操作は、ecobuild が確かめる）。
"""
from typing import Annotated


def part(
    branches: Annotated[list[dict], "ブランチ（branch list の行。タスクブランチも）"] = [],
    selected: Annotated[str | None, "選んでいるブランチ"] = None,
    default_base: Annotated[str | None, "既定のブランチ（タスクブランチの作成元）"] = None,
    creators: Annotated[dict | None, "ブランチを作った人（名前 → アカウント。account show の creators）"] = None,
    protection: Annotated[dict | None, "既定のブランチの保護（module protection。なければ null）"] = None,
    access: Annotated[dict | None, "アカウントと、できること（account show の結果：admin。管理者でなければ「削除…」を灰色に）"] = None,
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_action(
    action: Annotated[str, "押した操作：merge（取り込み・提出…）・delete（削除…）・upgrade（最新の仕様にする…）・protect（保護の設定…）・unprotect（保護を外す）・task（タスクブランチを開く）"],
    name: Annotated[str, "ブランチの名前"],
    task: Annotated[int, "タスクの番号（task のとき）"] = 0,
) -> None:
    if action not in ("merge", "delete", "upgrade", "protect", "unprotect", "task"):
        raise ValueError(f"知らない操作です：{action}")


def on_reload() -> None: ...
