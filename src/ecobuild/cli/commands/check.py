from typing import Annotated

from .._output import run_command

NAMES = {"generated": "生成ファイル", "conflict_markers": "衝突の印", "build": "ビルド", "test": "テスト"}


def command(
    build: Annotated[bool, "ビルドとテストも行う"] = True,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """PRを出す前の確認：生成ファイルがコミット済みか、衝突の印がないか、ビルド・テストが通るか。"""

    def action(inv):
        inv.info("確認しています…")
        return inv.module.check(build=build)

    return run_command("check", action, lambda r: "\n".join(
        f"{'OK' if i.ok else 'NG'} {NAMES[i.name]}" + (f"：{i.detail}" if i.detail else "") for i in r.items),
        json_output=json)
