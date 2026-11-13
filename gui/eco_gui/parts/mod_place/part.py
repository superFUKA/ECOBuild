"""変更をコミットするタスクブランチ（作業空間）を選ぶ欄。管理するファイル（エージェントの設定 等）を変える前に選ぶ。

選べるのは、このモジュールのタスクブランチの作業空間（確認用のものは除く）。「新しいタスクを作る…」で、そのための
タスクと作業空間を作る（new_task）。作業空間が1つもなければ、その旨と「新しいタスクを作る…」だけを出す。
"""
from typing import Annotated


def part(
    title: Annotated[str, "見出し"] = "コミットするタスクブランチ",
    note: Annotated[str, "横に添える説明"] = "",
    workspaces: Annotated[list[dict] | None, "このモジュールの作業空間（ecobuild module show の workspaces：path・branch・task・review）。読むまで null"] = None,
    value: Annotated[str | None, "選んでいる作業空間（なければ null）"] = None,
) -> None: ...


def on_changed(path: Annotated[str, "選んだ作業空間（選ばないなら空）"] = "") -> None: ...


def on_new_task() -> None: ...
