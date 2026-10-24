from typing import Annotated

from ecobuild_cli.kit import build_like, optional_argument

from ._stream import tool_output

AGENT = "change"


def command(
    *projects: Annotated[str, "対象のProject（--project と同じ）"],
    project: Annotated[str, "対象のProject（既定：Projectの中ならそのProject、それ以外は全体）"] = "",
    configuration: Annotated[str, "構成（Debug／Release等。既定：ビルド設定の構成、なければDebug）"] = "",
    profile: Annotated[str, "名前付きビルド設定（既定：ecobuild profile use で選んだもの）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """クリーンしてからビルドし直します。"""
    project = optional_argument(projects, project, "--project", json)
    with tool_output(json):
        return build_like("rebuild", project, configuration, profile, json)
