from typing import Annotated

from ecobuild.module import CHECK_NAMES
from .._output import run_command

NAMES = CHECK_NAMES


def command(
    build: Annotated[bool, "ビルドとテストも行う"] = True,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """提出の前の確認：生成ファイルが最新か、衝突の印がないか、ビルド・テストが通るか（コミット前でも使えます）。

    管理しない新しいファイル（コミットに含めないもの）も知らせます。ecobuild task submit も、既定でこの確認を行います。
    """

    def action(inv):
        inv.info("確認しています…")
        return inv.module.check(build=build)

    return run_command("check", action, lambda r: "\n".join(
        f"{'OK' if i.ok else 'NG'} {NAMES.get(i.name, i.name)}" + (f"：{i.detail}" if i.detail else "") for i in r.items),
        json_output=json)
