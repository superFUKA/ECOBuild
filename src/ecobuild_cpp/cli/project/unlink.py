from typing import Annotated

from ecobuild_cli.kit import run_command
from ._common import render_details, target_project


def command(
    link: Annotated[str, "外すリンク（project show に出る名前か id）"],
    project: Annotated[str, "対象のProject（既定：今いるProject、テスト用を除いてProjectが1つならそれ）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """Projectのリンクを外します。依存先のモジュールを丸ごと外すには ecobuild deps remove を使います。"""
    return run_command("project unlink", lambda inv: inv.module.unlink_project(target_project(inv, project), link),
                       render_details, json_output=json)
