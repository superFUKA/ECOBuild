import sys
from typing import Annotated

import click

from ...._output import run_command


def command(
    name: Annotated[str, "シークレットの名前（例：ECOBUILD_DEPS_TOKEN）"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """CIで使うシークレットを登録します。値は標準入力から読みます（端末なら入力を隠して尋ねます）。"""

    def action(inv):
        value = click.prompt("値", hide_input=True, err=True) if sys.stdin.isatty() else sys.stdin.read().strip()
        return {"name": inv.module.set_secret(name, value)}

    return run_command("ci secret set", action, lambda r: f"シークレット {r['name']} を登録しました",
                       json_output=json)
