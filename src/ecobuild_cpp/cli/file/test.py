from typing import Annotated

from ecobuild.errors import EcoBuildError
from ecobuild_cli.kit import run_command, usage_error

AGENT = "change"


def command(
    *paths: Annotated[str, "テストを作るファイル（ライブラリのヘッダー・ソース。今いるディレクトリからの相対。いくつでも）"],
    to: Annotated[str, "テストを置く場所（ファイルのパス。ファイルが1つのときだけ。既定は組のテスト用Projectの src/ の同じ構成の場所に <名前>Test.cpp）"] = "",
    dry_run: Annotated[bool, "作らずに、作る場所だけを表示する"] = False,
    json: Annotated[bool, "結果をJSONで出力する（作ったテストは paths、作らなかったファイルとわけは skipped）"] = False,
) -> int:
    """今あるヘッダー・ソースのテストを作ります（そのヘッダーを読み込むテストのひな形）。

    既定の場所は、組のテスト用Project（<ライブラリ>Test）の src/ の、同じ構成の場所です
    （include/<Project>/a/B.h・src/a/B.cpp → <ライブラリ>Test/src/a/BTest.cpp）。
    いくつものファイルを書くと、それぞれの既定の場所に作ります。作れないもの（テストが既にある等）は飛ばして知らせます
    （1つも作れなければ失敗）。
    """
    if not paths:
        return usage_error("テストを作るファイルを書いてください。", json)
    if to and len(paths) > 1:
        return usage_error("--to は、ファイルが1つのときだけ使えます。", json)

    def action(inv):
        made, skipped, first = [], [], None
        for path in paths:
            try:
                made += inv.module.add_test(inv.cwd / path, inv.cwd / to if to else None, dry_run=dry_run).paths
            except EcoBuildError as error:
                if len(paths) == 1:
                    raise
                first = first or error
                skipped.append({"path": path, "reason": error.message})
        if not made and first is not None:
            raise first
        return {"paths": made, "skipped": skipped}

    def render(r):
        return ("作る場所：" if dry_run else "テストを作りました：") + "\n" + "\n".join(f"  {p}" for p in r["paths"]) \
            + ("\n作らなかったもの：\n" + "\n".join(f"  {s['path']}：{s['reason']}" for s in r["skipped"]) if r["skipped"] else "")

    return run_command("file test", action, render, json_output=json)
