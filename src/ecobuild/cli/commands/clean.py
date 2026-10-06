from typing import Annotated

from .._output import build_like


def command(
    project: Annotated[str, "対象のProject（既定：Projectの中ならそのProject、それ以外は全体）"] = "",
    configuration: Annotated[str, "構成（Debug／Release等。既定：ビルド設定の構成、なければDebug）"] = "",
    profile: Annotated[str, "名前付きビルド設定（既定：ecobuild profile use で選んだもの）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ビルドの成果物を消します（中間ファイルの置き場所 build/ は残ります）。"""
    return build_like("clean", project, configuration, profile, json)
