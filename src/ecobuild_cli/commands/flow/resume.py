from typing import Annotated

from ..._output import run_command
from ._common import flows, render_run


def command(run: Annotated[str, "続ける実行"], json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """中断した（途中で止まった）実行を、中断した工程から続けます（エージェントの工程なら、同じエージェントを待ち直します）。"""
    return run_command("flow resume", lambda inv: flows(inv).resume(run), render_run, json_output=json)
