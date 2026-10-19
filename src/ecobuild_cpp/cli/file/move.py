from typing import Annotated

from ecobuild_cli.kit import move_file


def command(
    source: Annotated[str, "移動するファイル・フォルダー（中身ごと）"],
    destination: Annotated[str, "移動先（同じProjectの中）"],
    test: Annotated[bool, "ライブラリのヘッダー・ソースなら、対応するテスト（フォルダーならテスト用Projectの同じ構成のフォルダー）も移動する"] = True,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイル・フォルダーを移動（名前の変更）します。

    ライブラリのヘッダー・ソースなら、対応するテストも同じ構成の場所へ移します。移したファイルを読み込む #include も直します。
    """
    return move_file(source, destination, test, json)
