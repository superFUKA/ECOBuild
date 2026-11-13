from typing import Annotated

from ecobuild_cli.kit import test_like

AGENT = "change"


def command(
    configuration: Annotated[str, "構成（コマンドの {configuration} に入る。既定：ビルド設定の構成、なければDebug）"] = "",
    profile: Annotated[str, "名前付きビルド設定（既定：ecobuild profile use で選んだもの）"] = "",
    env: Annotated[str, "テストの環境に足す環境変数（名前=値。何度でも書ける：--env A=1 --env B=2。その前のビルドにも効く）"] = "",
    repeat: Annotated[int, "N 回流す（1回でも失敗したら失敗。--json の result.runs・error.details.runs に回ごとの成否と失敗したケース）"] = 1,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """テストします（ecobuild.toml の [commands] の test を実行します）。"""
    return test_like("", configuration, profile, json, empty="テストがありません", env=env, repeat=repeat)
