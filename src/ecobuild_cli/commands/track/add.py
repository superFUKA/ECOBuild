from typing import Annotated

from ..._output import run_command
from . import render


def command(
    *patterns: Annotated[str, "足すパターン（例：\"*.txt\"・\"data/**\"）"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """管理するファイルのパターンを足します。

    ecobuild.toml の [files] include に書きます。タスクブランチでコミットしてください。
    """
    return run_command("track add", lambda inv: inv.module.track(*patterns), render, json_output=json)
