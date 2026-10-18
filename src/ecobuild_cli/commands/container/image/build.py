from typing import Annotated

from ecobuild_bundle import container as _container
from ...._module import PROGRAM
from ...._output import Invocation, execute, split_list
from .._source import source
from ._render import render


def command(type: Annotated[str, "作る型（, で区切る。既定：すべての型）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """今の ECOBuild の型のイメージを作ります（あるものは作り直しません。1つ数分かかります）。

    作っておくと、作業空間のコンテナを初めて動かすときに待たずに済みます。
    """
    return execute("container image build", Invocation(json_output=json),
                   lambda inv: _container.build_images(split_list(type), source(), command=PROGRAM, progress=inv.info),
                   lambda r: render(r, None if r.built else "今の版のイメージはすべてあります"))
