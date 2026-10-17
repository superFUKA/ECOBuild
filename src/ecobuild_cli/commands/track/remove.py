from typing import Annotated

from ..._output import run_command
from . import render


def command(
    *patterns: Annotated[str, "外すパターン（ecobuild track の一覧にあるもの）"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """管理するファイルのパターンを外します。

    型の既定は [files] exclude に書きます。タスクブランチでコミットしてください。
    """
    return run_command("track remove", lambda inv: inv.module.track(*patterns, remove=True), render, json_output=json)
