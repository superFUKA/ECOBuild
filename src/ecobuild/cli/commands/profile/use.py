from typing import Annotated

from ..._output import run_command
from .list import render


def command(
    name: Annotated[str, "使うビルド設定の名前（none で選択を外す）"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """このPCで build・test・run 等に使うビルド設定を選びます（ecobuild.local.toml、コミットしない）。"""
    return run_command("profile use", lambda inv: inv.module.use_profile(None if name == "none" else name),
                       render, json_output=json)
