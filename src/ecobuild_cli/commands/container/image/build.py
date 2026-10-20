from typing import Annotated

from ecobuild_bundle import container as _container
from ...._module import PROGRAM
from pathlib import Path

from ...._output import Invocation, execute, split_list
from .._source import source
from ._render import render


def command(workspace: Annotated[str, "作る作業空間の場所（, で区切る。既定：このPCのコンテナにした作業空間すべて）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業空間のコンテナのイメージを今の作り方で作ります（あるものは作り直しません。1つ数分かかります）。

    作っておくと、作業空間のコンテナを初めて動かすときに待たずに済みます。
    """
    return execute("container image build", Invocation(json_output=json),
                   lambda inv: _container.build_images(tuple(Path(p) for p in split_list(workspace)), source(), command=PROGRAM, progress=inv.info),
                   lambda r: render(r, None if r.built else "今の版のイメージはすべてあります"))
