from typing import Annotated

from ecobuild_bundle import container as _container
from ...._module import PROGRAM
from ...._output import Invocation, execute
from .._source import source
from ._render import render


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """ECOBuild が作ったコンテナのイメージの一覧（今の版か・使っている作業空間）を表示します。

    イメージはモジュールごとに2つ：環境（ecobuild-env-<モジュール>。.ecobuild/container/Dockerfile から）と、
    それに ECOBuild を重ねたもの（ecobuild-<モジュール>）。名前に作り方のハッシュが入り、作り方が変わると新しく作ります。
    """
    return execute("container image list", Invocation(json_output=json),
                   lambda inv: _container.images(source(), command=PROGRAM), render)
