from typing import Annotated

from ..._output import run_command, usage_error

EVENTS = {"approve": "を承認しました", "request_changes": "に修正を依頼しました", "comment": "にコメントしました"}


def command(
    number: Annotated[int, "PRの番号"],
    approve: Annotated[bool, "承認する"] = False,
    request_changes: Annotated[bool, "修正を依頼する（--message が必要）"] = False,
    comment: Annotated[bool, "承認・修正依頼をせずにコメントする（--message が必要）"] = False,
    message: Annotated[str, "レビューの内容"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """PRのレビューの結果を返します（--approve・--request-changes・--comment のどれか1つ）。自分のPRは承認できません。"""
    chosen = [name for name, flag in (("approve", approve), ("request_changes", request_changes),
                                      ("comment", comment)) if flag]
    if len(chosen) != 1:
        return usage_error("--approve・--request-changes・--comment のどれか1つを指定してください。", json)
    event = chosen[0]
    return run_command("pr review", lambda inv: inv.module.review_pull_request(number, event, message),
                       lambda r: f"PR #{r.number} {EVENTS[event]}：{r.url}", json_output=json)
