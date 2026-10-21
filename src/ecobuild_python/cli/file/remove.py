from typing import Annotated

from ecobuild_cli.kit import remove_files


def command(
    *paths: Annotated[str, "削除するファイル"],
    test: Annotated[bool, "src/ のソースなら、対応するテストも削除する"] = True,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイルを削除します。src/ のソースなら、対応するテストも削除します。

    空になったフォルダーは片付けます（file add が作った空の __init__.py だけが残ったものも）。
    """
    return remove_files(paths, test, json)
