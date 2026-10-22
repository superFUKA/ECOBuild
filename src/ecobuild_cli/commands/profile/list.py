from typing import Annotated

from ..._output import run_command
from ...kit import render_profiles

AGENT = "read"


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """ビルド設定の一覧を表示します（* はこのPCで選んでいるもの）。"""
    return run_command("profile list", lambda inv: inv.module.profiles(), render_profiles, json_output=json)
