from typing import Annotated

from ecobuild_cli.kit import run_command


def command(
    path: Annotated[str, "テストを作るファイル（ライブラリのヘッダー・ソース。今いるディレクトリからの相対）"],
    to: Annotated[str, "テストを置く場所（ファイルのパス。既定は組のテスト用Projectの src/ の同じ構成の場所に <名前>Test.cpp）"] = "",
    dry_run: Annotated[bool, "作らずに、作る場所だけを表示する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """今あるヘッダー・ソースのテストを作ります（そのヘッダーを読み込むテストのひな形）。

    既定の場所は、組のテスト用Project（<ライブラリ>Test）の src/ の、同じ構成の場所です
    （include/<Project>/a/B.h・src/a/B.cpp → <ライブラリ>Test/src/a/BTest.cpp）。
    """

    def action(inv):
        return inv.module.add_test(inv.cwd / path, inv.cwd / to if to else None, dry_run=dry_run)

    def render(r):
        return ("作る場所：" if dry_run else "テストを作りました：") + "\n" + "\n".join(f"  {p}" for p in r.paths)

    return run_command("file test", action, render, json_output=json)
