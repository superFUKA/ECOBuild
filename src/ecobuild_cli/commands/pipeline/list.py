from typing import Annotated

from ..._output import run_command
from ._show import render

AGENT = "read"


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """パイプラインと、それを当てているタイミング（モジュールで共有するもの・このPCだけで足したもの）を表示します。"""
    return run_command("pipeline list", lambda inv: inv.module.pipelines(), render, json_output=json)
