from typing import Annotated

from ..._output import run_command
from ._common import flows, render_run


def command(run: Annotated[str, "取り消す実行"], json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """実行を取り消します。

    ほかの端末で動いている実行なら、止めてほしい印を置きます（工程の区切りで止まります。エージェントの工程は、待つのを
    やめてエージェントを止めます）。
    """
    return run_command("flow cancel", lambda inv: flows(inv).cancel(run), render_run, json_output=json)
