from typing import Annotated

from ecobuild_cli.kit import list_tests_like, test_like

from ._stream import tool_output

AGENT = "change"


def command(
    *tests: Annotated[str, "流すテスト（<テスト用Project> か <テスト用Project>.<Suite>.<Test>。* ? が使える。省略すると全部）"],
    project: Annotated[str, "対象のProject（既定：Projectの中ならそのProject、それ以外は全体。テスト用なら、流すテストは <Suite>.<Test> でよい）"] = "",
    list: Annotated[bool, "流せるテストの一覧を出す（流さない。名前はそのまま ecobuild test に渡せる）"] = False,
    configuration: Annotated[str, "構成（Debug／Release等。既定：ビルド設定の構成、なければDebug）"] = "",
    profile: Annotated[str, "名前付きビルド設定（既定：ecobuild profile use で選んだもの）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """テストします。流すテストを並べると、それだけ流します（ecobuild test CalcTest.Add.*）。

    テストの名前（cases の name）は <テスト用Project>.<Suite>.<Test> で、そのまま並べて流し直せます。
    --list はテスト用Projectのソースの TEST(…) 等から一覧を出します（ビルドしません）。
    """
    if list:
        return list_tests_like(project, configuration, profile, json)
    with tool_output(json):
        return test_like(project, configuration, profile, json, tests=tests, names=True,
                         empty="テスト用のProjectがありません（project add <名前> --kind library で、ライブラリとテスト用を作れます）")
