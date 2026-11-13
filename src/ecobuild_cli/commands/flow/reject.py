from typing import Annotated

from ..._output import missing, run_command
from ._common import flows, render_run


def command(run: Annotated[str, "人の答えを待っている実行"],
            to: Annotated[str, "差し戻す工程（待っている工程か、その前の工程。必須）"] = "",
            message: Annotated[str, "理由（必須。${vars.feedback} で読めます）"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """人の答え待ち（approval）の工程から、前の工程へ差し戻して続けます（理由は ${vars.feedback}）。"""
    if not to:
        return missing("--to", json)
    if not message:
        return missing("--message", json)
    return run_command("flow reject", lambda inv: flows(inv).reject(run, to, message), render_run, json_output=json)
