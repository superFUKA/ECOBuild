from typing import Annotated

from ecobuild_cli.kit import test_like


def command(
    configuration: Annotated[str, "構成（Debug／Release。既定：ビルド設定の構成、なければDebug）"] = "",
    profile: Annotated[str, "名前付きビルド設定（既定：ecobuild profile use で選んだもの）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """pytest でテストします（venv がなければ作ります）。"""
    return test_like("", configuration, profile, json,
                     empty="テストがありません（ecobuild file add src/<パッケージ>/<名前>.py で、tests/ にテストも作れます）")
