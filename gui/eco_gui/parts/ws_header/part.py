"""作業空間の窓の見出し：モジュールの名前と、今いる場所（タスクブランチとタスクの題・提出の確認中・ブランチ）。"""
from typing import Annotated


def part(
    module: Annotated[str, "作業空間のフォルダー（名前は、モジュールの情報がなければここから取る）"] = "",
    name: Annotated[str, "モジュールの名前"] = "",
    data: Annotated[dict, "状態（ecobuild status：branch・task・reviewing・reviewing_task）"] = {},
    task: Annotated[dict, "タスク（ecobuild task status：title）"] = {},
) -> None: ...
