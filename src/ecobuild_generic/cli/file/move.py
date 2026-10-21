from typing import Annotated

from ecobuild_cli.kit import move_file


def command(
    source: Annotated[str, "移動するファイル"],
    destination: Annotated[str, "移動先"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイルを移動（名前の変更）します。"""
    return move_file(source, destination, False, json)
