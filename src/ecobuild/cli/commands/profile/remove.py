from typing import Annotated

from ..._output import run_command
from .list import render


def command(
    name: Annotated[str, "ビルド設定の名前"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ビルド設定を削除します。"""
    return run_command("profile remove", lambda inv: inv.module.remove_profile(name), render, json_output=json)
