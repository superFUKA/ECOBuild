from typing import Annotated

from ...._output import run_command


def command(
    name: Annotated[str, "削除するシークレットの名前"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """CIで使うシークレットを削除します。"""
    return run_command("ci secret remove", lambda inv: {"name": inv.module.delete_secret(name)},
                       lambda r: f"シークレット {r['name']} を削除しました", json_output=json)
