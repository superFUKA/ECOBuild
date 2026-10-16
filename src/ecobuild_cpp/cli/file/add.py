from typing import Annotated

from ecobuild_cli.kit import add_files


def command(
    *paths: Annotated[str, "追加するファイル（Projectのディレクトリの中。今いるディレクトリからの相対）"],
    test: Annotated[bool, "ライブラリのソースなら、テスト用Projectにテストも作る"] = True,
    template: Annotated[str, "使うファイルテンプレート（ecobuild template list。既定は拡張子で選ぶ。指定するとテストは作らない）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイルをテンプレートから作ります。ライブラリの src/ にソースを足すと、テスト用Projectにテストも作ります。

    同じ名前のヘッダーとソースを一緒に足すと、ソースはそのヘッダーを相対パスで読み込みます（例：file add
    include/App/Foo.h src/Foo.cpp → #include "../include/App/Foo.h"）。
    """
    return add_files(paths, test, template, json)
