from typing import Annotated

from ecobuild.module import CHECK_NAMES
from .._output import run_command, split_list

AGENT = "change"

NAMES = CHECK_NAMES


def command(
    build: Annotated[bool, "ビルド・テストも行う（既定。--no-build で省く）"] = True,
    allow_dependency_mismatch: Annotated[bool, "手元の依存先が記録の版と違っても失敗にしない（知らせるだけ）"] = False,
    only: Annotated[str, "行う項目だけ（カンマ区切り：generated・conflict_markers・build・test。既定は全部）"] = "",
    tests: Annotated[str, "test で流す試験（カンマ区切り。型が絞れるとき。既定は全部）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """提出の前の確認：生成ファイルが最新か、衝突の印がないか、ビルド・テストが通るか（コミット前でも使えます）。

    管理しない新しいファイル（コミットに含めないもの）も知らせます。操作のたびに走らせるなら、項目を選んだパイプライン
    （ecobuild pipeline）を作って当てます（既定は何もしません）。--only・--tests で項目・試験を絞れます（そのときは、全部を
    通った版として残しません）。
    """

    def action(inv):
        inv.info("確認しています…")
        return inv.module.check(build=build, allow_dependency_mismatch=allow_dependency_mismatch,
                                only=() if only == "none" else split_list(only) or None, tests=split_list(tests))

    return run_command("check", action, lambda r: "\n".join(
        f"{'OK' if i.ok else 'NG'} {NAMES.get(i.name, i.name)}" + (f"：{i.detail}" if i.detail else "") for i in r.items),
        json_output=json)
