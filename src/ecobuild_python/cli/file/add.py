import os
from pathlib import Path
from typing import Annotated

from ecobuild_cli.kit import run_command


def command(
    *paths: Annotated[str, "追加するファイル（今いるディレクトリからの相対）"],
    test: Annotated[bool, "src/<パッケージ>/ のソースなら、tests/ の同じ構成の場所にテストも作る"] = True,
    json: Annotated[bool, "結果をJSONで出力する（作った __init__.py は result.packages にも入る）"] = False,
) -> int:
    """ファイルを作ります。src/<パッケージ>/ にソースを足すと、tests/ にテストも作ります。

    例：src/<パッケージ>/a/b.py を足すと、テスト tests/a/test_b.py も作ります。ビルドが setuptools のときだけ、
    新しいフォルダーに __init__.py も作ります（ひな形の hatchling は要りません）。
    """

    def action(inv):
        module = inv.module
        changed = module.add_files([inv.cwd / path for path in paths], test=test)
        added = [p for c in changed for p in c.paths]
        asked = {Path(os.path.abspath(inv.cwd / path)) for path in paths}
        packages = [p for p in added if Path(p).name == "__init__.py"
                    and Path(os.path.abspath(module.root / p)) not in asked]
        return {"paths": added, "packages": packages}

    def render(r):
        return "追加しました：\n" + "\n".join(
            f"  {p}" + ("（パッケージにするために作りました）" if p in r["packages"] else "") for p in r["paths"])

    return run_command("file add", action, render, json_output=json)
