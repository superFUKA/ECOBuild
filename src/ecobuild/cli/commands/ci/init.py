from typing import Annotated

from ..._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """GitHub Actions のワークフロー（Windows・Linuxで、CMakeだけで構成・ビルド・テスト）を作ります。"""
    return run_command("ci init", lambda inv: inv.module.write_ci(),
                       lambda r: f"{r.paths[0]} を作りました。作業空間でコミットし、PRで反映すると動きます", json_output=json)
