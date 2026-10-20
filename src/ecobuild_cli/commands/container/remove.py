from typing import Annotated

import ecobuild_container as _container
from ..._module import PROGRAM
from ..._output import run_command
from ._render import render, view


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業空間のコンテナを消します（ファイルは作業空間に残ります。コンテナの中で入れたものは消えます）。"""
    return run_command("container remove", lambda inv: view(_container.remove(inv.module.root, command=PROGRAM)),
                       lambda r: render(r, "コンテナを消しました"), json_output=json)
