from typing import Annotated

from ..._output import run_command
from ._common import flows, render_run


def command(run: Annotated[str, "失敗した実行"], json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """失敗した実行を、失敗した工程からやり直します（やり直しの回数 retries は数え直します）。"""
    return run_command("flow retry", lambda inv: flows(inv).retry(run), render_run, json_output=json)
