from typing import Annotated

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """エージェント向けの作業の手順を表示します。

    AGENTS.md から案内します。内容はモジュールの型と、このPCの ECOBuild に合わせたものです。
    """
    return run_command("agent guide", lambda inv: inv.module.agent_guide(), lambda r: r.text.rstrip("\n"),
                       json_output=json)
