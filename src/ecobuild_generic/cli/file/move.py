from typing import Annotated

from ecobuild_cli.kit import move_files

AGENT = "change"


def command(
    *paths: Annotated[str, "移動するファイルと、移動先（--into なら移動元だけ）"],
    into: Annotated[str, "このフォルダーへ移す（移動元をいくつでも書ける。名前は変えない）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイルを移動（名前の変更）します。

    ecobuild file move <移動元> <移動先>、いくつものファイルを1つのフォルダーへは file move <移動元…> --into <フォルダー>。
    """
    return move_files(paths, into, False, json)
