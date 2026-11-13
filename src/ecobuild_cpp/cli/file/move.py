from typing import Annotated

from ecobuild_cli.kit import move_files

AGENT = "change"


def command(
    *paths: Annotated[str, "移動するファイル・フォルダー（中身ごと）と、移動先（同じProjectの中。--into なら移動元だけ）"],
    into: Annotated[str, "このフォルダーへ移す（移動元をいくつでも書ける。名前は変えない）"] = "",
    test: Annotated[bool, "ライブラリのヘッダー・ソースなら、対応するテスト（フォルダーならテスト用Projectの同じ構成のフォルダー）も移動する"] = True,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイル・フォルダーを移動（名前の変更）します。

    ecobuild file move <移動元> <移動先>、いくつものものを1つのフォルダーへは file move <移動元…> --into <フォルダー>。
    ライブラリのヘッダー・ソースなら、対応するテストも同じ構成の場所へ移します。移したファイルを読み込む #include も直します。
    """
    return move_files(paths, into, test, json)
