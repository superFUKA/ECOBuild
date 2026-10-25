from typing import Annotated

from ecobuild_cli.kit import test_like

from ._stream import tool_output

AGENT = "change"


def command(
    *tests: Annotated[str, "流すテスト（<テスト用Project> か <テスト用Project>.<Suite>.<Test>。* ? が使える。省略すると全部）"],
    project: Annotated[str, "対象のProject（既定：Projectの中ならそのProject、それ以外は全体。テスト用なら、流すテストは <Suite>.<Test> でよい）"] = "",
    configuration: Annotated[str, "構成（Debug／Release等。既定：ビルド設定の構成、なければDebug）"] = "",
    profile: Annotated[str, "名前付きビルド設定（既定：ecobuild profile use で選んだもの）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """テストします。流すテストを並べると、それだけ流します（ecobuild test CalcTest.Add.*）。

    テストの名前（cases の name）は <テスト用Project>.<Suite>.<Test> で、そのまま並べて流し直せます。
    """
    with tool_output(json):
        return test_like(project, configuration, profile, json, tests=tests, names=True,
                         empty="テスト用のProjectがありません（project add <名前> --kind library で、ライブラリとテスト用を作れます）")
