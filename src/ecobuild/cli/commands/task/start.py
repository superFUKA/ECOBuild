from typing import Annotated

from ..._output import run_command


def command(
    issue: Annotated[int, "Issueの番号"],
    base: Annotated[str, "作成元のブランチ（既定はecobuild.tomlのdefault_base）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """Issueの作業空間（task/<番号>）を作り、切り替えます。既にあれば切り替えるだけです。"""
    return run_command("task start", lambda inv: inv.module.task(issue).start(base=base or None),
                       lambda r: f"作業空間 {r.branch} に切り替えました（作成元 {r.base}）", json_output=json)
