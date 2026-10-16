from typing import Annotated

from ecobuild_cli.kit import remove_files


def command(
    *paths: Annotated[str, "削除するファイル"],
    test: Annotated[bool, "ライブラリのソースなら、対応するテストファイルも削除する"] = True,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイルを削除します。ライブラリのソースなら、対応するテストファイルも削除します。"""
    return remove_files(paths, test, json)
