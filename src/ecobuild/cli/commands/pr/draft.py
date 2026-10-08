from typing import Annotated

from ..._output import optional_argument, run_command


def command(
    *number: Annotated[int, "PRの番号（--pr と同じ）"],
    pr: Annotated[int, "PRの番号（既定：今いる作業空間のPR）"] = 0,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """PRを下書きに戻します（マージできなくなります。戻すときは ecobuild pr ready）。"""
    pr = optional_argument(number, pr, "--pr", json)
    return run_command("pr draft", lambda inv: inv.module.set_pull_request_draft(pr or None, draft=True),
                       lambda r: f"PR #{r.number} を下書きにしました", json_output=json)
