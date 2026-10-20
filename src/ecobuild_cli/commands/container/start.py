from typing import Annotated

import ecobuild_container as _container
from ..._module import PROGRAM
from ..._output import run_command
from ._render import render, view
from ._source import source


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業空間のコンテナを動かします（なければ作ります）。

    コンテナの元（イメージ）は、モジュールの .ecobuild/container/Dockerfile（環境）に git・gh・ECOBuild（このPCと同じ版）を
    重ねて作ります。作るのは最初の1回と、環境・ECOBuild が変わったときだけで、数分かかります。
    """
    return run_command("container start",
                       lambda inv: view(_container.start(inv.module.root, command=PROGRAM, source=source(),
                                                         progress=inv.info)),
                       lambda r: render(r, "コンテナを動かしました"), json_output=json)
