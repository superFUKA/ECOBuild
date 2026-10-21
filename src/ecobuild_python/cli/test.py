from typing import Annotated

from ecobuild_cli.kit import test_like


def command(
    *tests: Annotated[str, "流すテスト（ファイル・フォルダ・tests/x.py::test_a。省略すると全部）"],
    configuration: Annotated[str, "構成（Debug／Release。既定：ビルド設定の構成、なければDebug）"] = "",
    profile: Annotated[str, "名前付きビルド設定（既定：ecobuild profile use で選んだもの）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """pytest でテストします（venv がなければ作ります）。変えたところのテストだけ流すなら、ファイル等を並べます。"""
    return test_like("", configuration, profile, json,
                     tests=tests, empty="テストがありません（ecobuild file add src/<パッケージ>/<名前>.py で、tests/ にテストも作れます）")
