from typing import Annotated

from ..._output import run_command
from ._show import render


def command(
    name: Annotated[str, "消すパイプラインの名前"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """パイプラインを消します（当てていたタイミングからも外します。タスクブランチでだけ）。"""
    return run_command("pipeline remove", lambda inv: inv.module.remove_pipeline(name), render, json_output=json)
