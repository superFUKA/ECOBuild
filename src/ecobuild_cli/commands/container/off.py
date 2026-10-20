from typing import Annotated

import ecobuild_container as _container
from ..._module import PROGRAM
from ..._output import run_command
from ._render import render, view


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """今いる作業空間をコンテナにしません。作ったコンテナも消します（ファイルは作業空間に残ります）。"""
    return run_command("container off", lambda inv: view(_container.choose(inv.module.root, False, command=PROGRAM)),
                       lambda r: render(r, "コンテナにしないようにしました"), json_output=json)
