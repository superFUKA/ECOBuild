from typing import Annotated

from ..._output import missing, optional_argument, run_command


def command(
    *number: Annotated[int, "Issueの番号（--issue と同じ）"],
    issue: Annotated[int, "Issueの番号（既定：今いる作業空間）"] = 0,
    message: Annotated[str, "コメント"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスク（Issue）にコメントを残します（作業の記録・申し送り。ecobuild task status で読めます）。"""
    issue = optional_argument(number, issue, "--issue", json)
    if not message:
        return missing("--message", json)
    return run_command("task comment", lambda inv: inv.module.comment_task(issue or None, message),
                       lambda r: f"#{r.number} にコメントしました：{r.url}", json_output=json)
