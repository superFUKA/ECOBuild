from typing import Annotated

from ..._output import optional_argument, run_command


def command(
    *number: Annotated[int, "PRの番号（--pr と同じ）"],
    pr: Annotated[int, "PRの番号（既定：今いる作業空間のPR）"] = 0,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """下書きのPRを、レビュー・マージできる状態にします。"""
    pr = optional_argument(number, pr, "--pr", json)
    return run_command("pr ready", lambda inv: inv.module.set_pull_request_draft(pr or None, draft=False),
                       lambda r: f"PR #{r.number} の下書きを解除しました：{r.url}", json_output=json)
