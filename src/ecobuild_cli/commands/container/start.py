from typing import Annotated

from ecobuild_bundle import container as _container
from ..._module import PROGRAM
from ..._output import run_command
from ._render import render
from ._source import source


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業空間のコンテナを動かします（なければ作ります）。

    コンテナの元（イメージ）は、型ごとに Ubuntu に git・gh・ECOBuild（このPCと同じ版）と型のツールを入れて作ります。
    作るのは最初の1回だけで、数分かかります。
    """
    return run_command("container start",
                       lambda inv: _container.start(inv.module.root, command=PROGRAM, source=source(),
                                                    progress=inv.info),
                       lambda r: render(r, "コンテナを動かしました"), json_output=json)
