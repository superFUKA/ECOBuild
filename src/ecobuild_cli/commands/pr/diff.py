from typing import Annotated

from ..._output import optional_argument, run_command


def command(
    *number: Annotated[int, "PRの番号（--pr と同じ）"],
    pr: Annotated[int, "PRの番号（既定：今いる作業空間のPR）"] = 0,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """PRの差分（GitHubにある内容）を表示します。"""
    pr = optional_argument(number, pr, "--pr", json)
    return run_command("pr diff", lambda inv: inv.module.pull_request_diff(pr or None),
                       lambda r: r or "差分はありません", json_output=json)
