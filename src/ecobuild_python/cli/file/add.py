from typing import Annotated

from ecobuild_cli.kit import add_files


def command(
    *paths: Annotated[str, "追加するファイル（今いるディレクトリからの相対）"],
    test: Annotated[bool, "src/<パッケージ>/ のソースなら、tests/ の同じ構成の場所にテストも作る"] = True,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイルを作ります。src/<パッケージ>/ にソースを足すと、tests/ にテストも作ります。

    例：src/<パッケージ>/a/b.py を足すと、テスト tests/a/test_b.py も作ります（足りない __init__.py も作ります）。
    """
    return add_files(paths, test, "", json)
