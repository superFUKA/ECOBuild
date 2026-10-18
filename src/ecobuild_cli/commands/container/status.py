from typing import Annotated

from ecobuild_bundle import container as _container
from ..._output import run_command
from ._render import render


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """状態を表示します（コンテナにするか・コンテナが動いているか）。"""
    return run_command("container status", lambda inv: _container.show(inv.module.root),
                       lambda r: render(r, None), json_output=json)
