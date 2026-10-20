from typing import Annotated

import ecobuild_container as _container
from ..._output import run_command
from ._render import render, view
from ._source import source


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """状態を表示します（コンテナにするか・コンテナが動いているか）。"""
    return run_command("container status", lambda inv: view(_container.show(inv.module.root, source=source())),
                       lambda r: render(r, None), json_output=json)
