from typing import Annotated

from ecobuild_cpp import cpp

from ecobuild_cli.kit import run_command
from .list import render


def command(
    name: Annotated[str, "テンプレート名（file add --template で使う。同じ名前なら差し替える）"],
    source: Annotated[str, "元にするファイル（今いるディレクトリからの相対）"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイルテンプレートを登録します。管理ファイルが変わるので、作業空間でコミットしてください。

    中の {{header}}・{{suite}}・{{name}}・{{project}} は、file add のときに読み込むヘッダー・ファイル名・
    ファイル名・Project名に置き換わります。ECOBuildの既定のテンプレート（header・source 等）も同じ名前で差し替えられます。
    """
    return run_command("template add", lambda inv: cpp(inv.module).add_template(name, inv.cwd / source), render,
                       json_output=json)
