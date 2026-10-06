from typing import Annotated

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """CI（ecobuild ci init で作ったワークフロー）をやめます。作業空間でコミットし、PRで反映してください。"""
    return run_command("ci remove", lambda inv: inv.module.remove_ci(),
                       lambda r: f"{r.paths[0]} を消しました", json_output=json)
