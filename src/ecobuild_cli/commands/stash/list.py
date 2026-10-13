from typing import Annotated

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """退避した変更の一覧を表示します。"""
    return run_command("stash list", lambda inv: list(inv.module.stashes()),
                       lambda r: "\n".join(f"{i}: {m}" for i, m in enumerate(r)) or "退避した変更はありません",
                       json_output=json)
