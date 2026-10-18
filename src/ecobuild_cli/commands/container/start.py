from typing import Annotated

from ecobuild_bundle import container as _container
from ..._module import PROGRAM
from ..._output import run_command
from ._render import render


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業空間のコンテナを動かします（なければ作ります）。"""
    return run_command("container start", lambda inv: _container.start(inv.module.root, command=PROGRAM),
                       lambda r: render(r, "コンテナを動かしました"), json_output=json)
