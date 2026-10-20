from typing import Annotated

import ecobuild_container as _container
from ..._module import PROGRAM
from ..._output import run_command
from ._render import render, view


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業空間のコンテナを止めます（消しません。container start でまた動かせます）。"""
    return run_command("container stop", lambda inv: view(_container.stop(inv.module.root, command=PROGRAM)),
                       lambda r: render(r, "コンテナを止めました"), json_output=json)
