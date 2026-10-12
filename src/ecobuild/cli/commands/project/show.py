from typing import Annotated

from ..._output import optional_argument, run_command
from ._common import render_details, target_project


def command(
    *projects: Annotated[str, "対象のProject（--project と同じ）"],
    project: Annotated[str, "対象のProject（既定：今いるProject、テスト用を除いてProjectが1つならそれ）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """Projectの設定（ソース・定義・インクルード・リンク・PCH 等）を表示します。"""
    project = optional_argument(projects, project, "--project", json)
    return run_command("project show", lambda inv: inv.module.project_details(target_project(inv, project)),
                       render_details, json_output=json)
