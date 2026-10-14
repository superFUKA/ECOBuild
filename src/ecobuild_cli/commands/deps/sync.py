from typing import Annotated

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """手元の依存先を記録の版に合わせます（ない依存先はcloneし、作業版・変更のあるものは触りません）。"""
    return run_command("deps sync", lambda inv: list(inv.module.sync_dependencies()),
                       lambda r: "\n".join(f"{d.name}：{d.action}" + (f"（{d.reason}）" if d.reason else "") for d in r)
                       or "依存先はありません", json_output=json)
