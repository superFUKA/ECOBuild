from typing import Annotated

from ..._output import run_command


def command(
    *paths: Annotated[str, "追加するファイル（Projectのディレクトリの中。今いるディレクトリからの相対）"],
    test: Annotated[bool, "ソースなら、テストも作る（C++：テスト用Project、Python：tests/ の同じ構成の場所）"] = True,
    template: Annotated[str, "使うファイルテンプレート（ecobuild template list。既定は拡張子で選ぶ。指定するとテストは作らない）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイルをテンプレートから作ります。ライブラリの src/ にソースを足すと、テスト用Projectにテストも作ります。

    Python では src/<パッケージ>/a/b.py を足すと、テスト tests/a/test_b.py も作ります。

    同じ名前のヘッダーとソースを一緒に足すと、ソースはそのヘッダーを相対パスで読み込みます（例：file add
    include/App/Foo.h src/Foo.cpp → #include "../include/App/Foo.h"）。
    """

    def action(inv):
        changed = inv.module.add_files([inv.cwd / path for path in paths], test=test, template=template or None)
        return {"paths": [p for c in changed for p in c.paths]}

    return run_command("file add", action, lambda r: "追加しました：\n" + "\n".join(f"  {p}" for p in r["paths"]),
                       json_output=json)
