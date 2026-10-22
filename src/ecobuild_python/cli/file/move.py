from typing import Annotated

from ecobuild_cli.kit import move_file

AGENT = "change"


def command(
    source: Annotated[str, "移動するファイル"],
    destination: Annotated[str, "移動先"],
    test: Annotated[bool, "src/ のソースなら、対応するテストも移動する（テストの import も直す）"] = True,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイルを移動（名前の変更）します。src/ のソースなら、対応するテストも移動します。"""
    return move_file(source, destination, test, json)
