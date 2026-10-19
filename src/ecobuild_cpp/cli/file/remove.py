from typing import Annotated

from ecobuild_cli.kit import remove_files


def command(
    *paths: Annotated[str, "削除するファイル・フォルダー（中身ごと）"],
    test: Annotated[bool, "ライブラリのヘッダー・ソースなら、対応するテストファイルも削除する（ほかに対応するファイルが残らないとき）"] = True,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイル・フォルダーを削除します。ライブラリのヘッダー・ソースなら、対応するテストファイルも削除します。"""
    return remove_files(paths, test, json)
