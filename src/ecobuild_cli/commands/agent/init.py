from typing import Annotated

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """AGENTS.md（エージェントが最初に読む、守ることの核）を作り直します。作業空間でコミットしてください。

    詳しい手順は AGENTS.md に写さず、ecobuild agent guide がその時の ECOBuild に合わせて出します。
    """
    return run_command("agent init", lambda inv: inv.module.write_agents(),
                       lambda r: "AGENTS.md を作りました", json_output=json)
