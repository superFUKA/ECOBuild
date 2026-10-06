from typing import Annotated

from ...._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """登録済みのシークレットの名前を表示します（値は表示できません）。"""
    return run_command("ci secret list", lambda inv: inv.module.secrets(),
                       lambda r: "\n".join(r) or "シークレットはありません", json_output=json)
