from typing import Annotated

from ecobuild import config as _config
from ecobuild_bundle import container as _container
from ..._module import PROGRAM
from ..._output import lines, run_command
from ._source import source


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """この作業空間のコンテナのイメージの作り方を表示します。

    モジュールの環境（.ecobuild/container/Dockerfile。なければ型のひな型）と、それに ECOBuild を重ねた層、
    それぞれのイメージの名前（作り方のハッシュ）。環境はコミットしてほかの端末と共有します。
    """
    return run_command("container recipe", lambda inv: _container.recipe(inv.module.root, source()), _render,
                       json_output=json)


def _render(r) -> str:
    return lines(
        f"環境：{_config.CONTAINER_DOCKERFILE if r.context else f'型のひな型（{PROGRAM} module upgrade で {_config.CONTAINER_DOCKERFILE} に置けます）'}",
        f"環境のイメージ：{r.environment}",
        f"コンテナのイメージ（環境＋ECOBuild）：{r.image}",
        "",
        r.dockerfile.rstrip(),
    )
