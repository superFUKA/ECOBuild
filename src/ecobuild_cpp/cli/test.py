from typing import Annotated

from ecobuild_cli.kit import optional_argument, test_like

AGENT = "change"


def command(
    *projects: Annotated[str, "対象のProject（--project と同じ）"],
    project: Annotated[str, "対象のProject（既定：Projectの中ならそのProject、それ以外は全体）"] = "",
    configuration: Annotated[str, "構成（Debug／Release等。既定：ビルド設定の構成、なければDebug）"] = "",
    profile: Annotated[str, "名前付きビルド設定（既定：ecobuild profile use で選んだもの）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """テストします。"""
    project = optional_argument(projects, project, "--project", json)
    return test_like(project, configuration, profile, json,
                     empty="テスト用のProjectがありません（project add <名前> --kind library で、ライブラリとテスト用を作れます）")
