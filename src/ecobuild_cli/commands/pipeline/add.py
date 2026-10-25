from typing import Annotated

from ecobuild import config

from ..._output import run_command, split_list
from ._show import render


def command(
    name: Annotated[str, "パイプラインの名前（例：quick、full）"],
    steps: Annotated[str, "手順（カンマ区切り・この順に：generated・conflict_markers・build・test）"] = "",
    tests: Annotated[str, "test で流す試験（カンマ区切り。型が絞れるとき。既定は全部）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """パイプラインを作ります（同じ名前があれば中身を置き換えます）。

    手順は、生成ファイルが最新か（generated）・衝突の印がないか（conflict_markers）・ビルド（build）・テスト（test）
    から選びます。作っただけでは走りません：ecobuild pipeline run で走らせるか、ecobuild pipeline on でタイミングに
    当てます。ecobuild.toml を変えるので、タスクブランチでだけ使えます（コミットして提出すると共有されます）。
    """
    return run_command("pipeline add", lambda inv: inv.module.set_pipeline(
        config.Pipeline(name, tuple(split_list(steps)), tuple(split_list(tests)))), render, json_output=json)
