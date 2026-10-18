from typing import Annotated

from ecobuild_bundle import container as _container
from ...._module import PROGRAM
from ...._output import Invocation, execute
from .._source import source
from ._render import render


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """古いイメージ（今の ECOBuild の版でなく、どのコンテナも使っていないもの）を消します。"""
    return execute("container image prune", Invocation(json_output=json),
                   lambda inv: _container.prune_images(source(), command=PROGRAM),
                   lambda r: render(r, None if r.removed else "消す古いイメージはありません"))
