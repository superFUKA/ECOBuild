from typing import Annotated

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """係が画面なしで動かしている、この作業空間のエージェントを止めます（返答を終えさせてから）。

    agent start --app で起動したものに使います（進行役の作業役は agent team close・restart・takeover で）。
    """
    from .team import _forward
    return run_command("agent stop", lambda inv: _forward.serve(inv, ["agent", "stop"]),
                       lambda r: "エージェントを止めました。", json_output=json)
