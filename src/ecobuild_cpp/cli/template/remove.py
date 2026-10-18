from typing import Annotated

from ecobuild_cpp import cpp

from ecobuild_cli.kit import run_command
from .list import render


def command(
    name: Annotated[str, "外すテンプレート"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ファイルテンプレートを外します（ECOBuildの既定のものは外せません）。

    タスクブランチで行い、変わった ECOBuild のファイル（.ecobuild の中）はそのままコミットします（Push はしません）。"""
    return run_command("template remove", lambda inv: cpp(inv.module).remove_template(name), render, json_output=json)
