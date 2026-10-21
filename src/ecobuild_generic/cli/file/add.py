from typing import Annotated

from ecobuild_cli.kit import add_files


def command(
    *paths: Annotated[str, "作るファイル（拡張子込み。今いるディレクトリからの相対）"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """書いた名前のファイルを空で作ります（例：ecobuild file add docs/memo.md）。"""
    return add_files(paths, False, "", json)
