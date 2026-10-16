from typing import Annotated

from ecobuild_cli.kit import build_like


def command(
    configuration: Annotated[str, "構成（Debug／Release。既定：ビルド設定の構成、なければDebug）"] = "",
    profile: Annotated[str, "名前付きビルド設定（既定：ecobuild profile use で選んだもの）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ビルドします（venv を用意し、Release なら配布用のパッケージ〔wheel・sdist〕も作ります）。"""
    return build_like("build", "", configuration, profile, json)
