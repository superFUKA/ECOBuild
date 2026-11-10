from typing import Annotated

from ecobuild_cli.kit import list_tests_like


def command(
    configuration: Annotated[str, "構成（Debug／Release。既定：ビルド設定の構成、なければDebug）"] = "",
    profile: Annotated[str, "名前付きビルド設定（既定：ecobuild profile use で選んだもの）"] = "",
    json: Annotated[bool, "結果をJSONで出力する（result.tests：name・file・line）"] = False,
) -> int:
    """流せるテストの一覧を表示します（流しません）。

    pytest が集めるテストの一覧です（venv がなければ作ります）。名前は pytest の nodeid で、そのまま ecobuild test に
    渡せます。
    """
    return list_tests_like("", configuration, profile, json, command="tests")
