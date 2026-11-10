from typing import Annotated

from ecobuild_cli.kit import list_tests_like


def command(
    project: Annotated[str, "対象のProject（既定：全体）"] = "",
    configuration: Annotated[str, "構成（Debug／Release等。既定：ビルド設定の構成、なければDebug）"] = "",
    profile: Annotated[str, "名前付きビルド設定（既定：ecobuild profile use で選んだもの）"] = "",
    json: Annotated[bool, "結果をJSONで出力する（result.tests：name・file・line）"] = False,
) -> int:
    """流せるテストの一覧を表示します（流しません。ビルドもしません）。

    テスト用Projectのソースの TEST(…) 等から一覧を出します。名前は <テスト用Project>.<Suite>.<Test> で、そのまま
    ecobuild test に渡せます。
    """
    return list_tests_like(project, configuration, profile, json, command="tests")
