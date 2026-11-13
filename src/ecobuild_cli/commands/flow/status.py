from typing import Annotated

from ..._output import run_command, usage_error
from ._common import flows, render_run

AGENT = "read"


def command(*run: Annotated[str, "実行（省けば、この作業空間のいちばん新しい実行）"],
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """流れの実行の様子（工程ごとの状態・回数・最後の文・次にできること）を表示します。"""
    if len(run) > 1:
        return usage_error("実行は1つだけ書けます。", json)
    return run_command("flow status", lambda inv: flows(inv).status(run[0] if run else ""), render_run, json_output=json)
