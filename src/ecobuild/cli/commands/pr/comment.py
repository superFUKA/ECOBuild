from typing import Annotated

from ..._output import missing, optional_argument, run_command


def command(
    *number: Annotated[int, "PRの番号（--pr と同じ）"],
    pr: Annotated[int, "PRの番号（既定：今いる作業空間のPR）"] = 0,
    message: Annotated[str, "コメント"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """PRにコメントを残します（レビューの結果を返すなら ecobuild pr review）。"""
    pr = optional_argument(number, pr, "--pr", json)
    if not message:
        return missing("--message", json)
    return run_command("pr comment", lambda inv: inv.module.comment_pull_request(pr or None, message),
                       lambda r: f"PR #{r.number} にコメントしました：{r.url}", json_output=json)
