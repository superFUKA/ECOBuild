from typing import Annotated

import ecobuild_container as _container
from ..._module import PROGRAM
from ..._output import run_command
from ._render import render, view


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """今いる作業空間をコンテナにします（選ぶだけ。コンテナは container start で作ります）。"""
    return run_command("container on", lambda inv: view(_container.choose(inv.module.root, True, command=PROGRAM)),
                       lambda r: render(r, "コンテナにしました"), json_output=json)
