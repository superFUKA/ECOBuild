from typing import Annotated

from ecobuild_cli.kit import run_like


def command(
    configuration: Annotated[str, "構成（Debug／Release。既定：ビルド設定の構成、なければDebug）"] = "",
    profile: Annotated[str, "名前付きビルド設定（既定：ecobuild profile use で選んだもの）"] = "",
    arguments: Annotated[str, "プログラムへ渡す引数（1つの文字列）"] = "",
    json: Annotated[bool, "結果をJSONで出力する（プログラムの出力はresult.outputに入る）"] = False,
) -> int:
    """pyproject.toml の [project.scripts] のコマンドを、venv で実行します。"""
    return run_like("", configuration, profile, arguments, json)
