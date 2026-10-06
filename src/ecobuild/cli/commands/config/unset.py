from typing import Annotated

from .... import tooling
from ..._output import Invocation, execute
from .list import render


def command(
    key: Annotated[str, "項目"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ツールの設定を消します（既定に戻します）。"""
    return execute("config unset", Invocation(json_output=json), lambda inv: tooling.set_config(key, None), render)
