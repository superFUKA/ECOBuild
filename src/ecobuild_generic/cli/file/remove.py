from typing import Annotated

from ecobuild_cli.kit import remove_files


def command(
    *paths: Annotated[str, "削除するファイル"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイルを削除します。"""
    return remove_files(paths, False, json)
