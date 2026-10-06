from typing import Annotated

from ..._output import run_command


def command(
    *paths: Annotated[str, "追加するファイル（Projectのディレクトリの中。今いるディレクトリからの相対）"],
    test: Annotated[bool, "ライブラリのソースなら、テスト用Projectにテストも作る"] = True,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイルをテンプレートから作ります。ライブラリの src/ にソースを足すと、テスト用Projectにテストも作ります。"""

    def action(inv):
        changed = [inv.module.add_file(inv.cwd / path, test=test) for path in paths]
        return {"paths": [p for c in changed for p in c.paths]}

    return run_command("file add", action, lambda r: "追加しました：\n" + "\n".join(f"  {p}" for p in r["paths"]),
                       json_output=json)
