"""作業空間の「提出」のタブの見出し：このタスクブランチの提出（PR）の番号と状態（提出中・下書き・取り込み済み・閉じた）、取り込み先、URL。

まだ提出していなければ、そう出す。提出に入るコミットの数（まだ送っていないコミットがあれば、その注意）も出す。"""
from typing import Annotated


def part(
    status: Annotated[dict, "状態（ecobuild status：pull_request〔number・state・draft・partial・base・url〕・task・ahead・reviewing）"] = {},
) -> None: ...


def on_copied(url: Annotated[str, "写した URL"]) -> None: ...
