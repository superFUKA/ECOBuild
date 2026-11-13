from typing import Annotated

from ..._output import run_command
from ._common import flows, render_run


def command(run: Annotated[str, "人の答えを待っている実行"],
            message: Annotated[str, "添える文（${steps.<工程>.out.message} で読めます）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """人の答え待ち（approval）の工程を通して、続きを進めます。"""
    return run_command("flow approve", lambda inv: flows(inv).approve(run, message), render_run, json_output=json)
