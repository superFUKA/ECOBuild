from typing import Annotated

from ecobuild_cli.kit import move_file


def command(
    source: Annotated[str, "移動するファイル"],
    destination: Annotated[str, "移動先（同じProjectの中）"],
    test: Annotated[bool, "ライブラリのソースなら、対応するテストファイルも移動する"] = True,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイルを移動（名前の変更）します。ライブラリのソースなら、対応するテストファイルも移動します。"""
    return move_file(source, destination, test, json)
