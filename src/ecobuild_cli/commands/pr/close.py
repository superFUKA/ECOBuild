from typing import Annotated

from ..._output import optional_argument, run_command


def command(
    *number: Annotated[int, "PRの番号（--pr と同じ）"],
    pr: Annotated[int, "PRの番号（既定：今いる作業空間のPR）"] = 0,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """PRを閉じます（ブランチ・作業空間・Issueはそのまま。作業をやめるなら ecobuild task drop）。"""
    pr = optional_argument(number, pr, "--pr", json)
    return run_command("pr close", lambda inv: inv.module.close_pull_request(pr or None),
                       lambda r: f"PR #{r.number} を閉じました", json_output=json)
