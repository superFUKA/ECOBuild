from typing import Annotated

from ecobuild_cli.kit import run_like

AGENT = "change"


def command(
    configuration: Annotated[str, "構成（コマンドの {configuration} に入る。既定：ビルド設定の構成、なければDebug）"] = "",
    profile: Annotated[str, "名前付きビルド設定（既定：ecobuild profile use で選んだもの）"] = "",
    arguments: Annotated[str, "プログラムへ渡す引数（1つの文字列。コマンドの {arguments} に入る）"] = "",
    env: Annotated[str, "プログラムの環境に足す環境変数（名前=値。何度でも書ける：--env A=1 --env B=2。その前のビルドにも効く）"] = "",
    json: Annotated[bool, "結果をJSONで出力する（プログラムの出力はresult.outputに入る）"] = False,
) -> int:
    """実行します（ecobuild.toml の [commands] の run を実行します）。"""
    return run_like("", configuration, profile, arguments, json, env=env)
