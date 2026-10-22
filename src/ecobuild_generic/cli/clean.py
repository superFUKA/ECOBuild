from typing import Annotated

from ecobuild_cli.kit import build_like

AGENT = "change"


def command(
    configuration: Annotated[str, "構成（コマンドの {configuration} に入る。既定：ビルド設定の構成、なければDebug）"] = "",
    profile: Annotated[str, "名前付きビルド設定（既定：ecobuild profile use で選んだもの）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """クリーンします（[commands] の clean を実行します）。"""
    return build_like("clean", "", configuration, profile, json)
