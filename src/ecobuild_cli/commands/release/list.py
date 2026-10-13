from typing import Annotated

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """GitHubのリリースの一覧を表示します。"""
    return run_command("release list", lambda inv: list(inv.module.releases()),
                       lambda r: "\n".join(f"{x.tag} {x.name}" + ("（最新）" if x.latest else "") for x in r)
                       or "リリースはありません", json_output=json)
