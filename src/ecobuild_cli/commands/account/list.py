from typing import Annotated

from ecobuild_bundle.tooling import gh_accounts
from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """このPCの gh でログインしている GitHub のアカウントを表示します（作業空間に結び付けられるもの）。

    別のアカウントを足すには gh auth login（使用中のアカウントも切り替わるので、gh auth switch で戻します）。
    """
    return run_command("account list", lambda inv: gh_accounts(), lambda r: "\n".join(
        f"  {a['login']}" + ("（gh の使用中）" if a["active"] else "") for a in r) or "ログインしているアカウントはありません（gh auth login）",
        json_output=json)
