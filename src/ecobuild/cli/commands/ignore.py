from typing import Annotated

from .._output import run_command


def command(
    *patterns: Annotated[str, ".gitignore に足すパターン"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """gitの管理から外すファイルのパターンを .gitignore に足します（作業空間でコミットしてください）。"""
    return run_command("ignore", lambda inv: list(inv.module.ignore(*patterns)),
                       lambda r: ("追加しました：" + ", ".join(r)) if r else "追加するものはありません（既にあります）",
                       json_output=json)
