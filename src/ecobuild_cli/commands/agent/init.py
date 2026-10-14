from typing import Annotated

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """AGENTS.md（エージェント向けのECOBuildの使い方）を作り直します。作業空間でコミットしてください。"""
    return run_command("agent init", lambda inv: inv.module.write_agents(),
                       lambda r: "AGENTS.md を作りました", json_output=json)
