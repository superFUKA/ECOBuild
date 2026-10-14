from typing import Annotated

from ..._output import lines, optional_argument, run_command
from ..task.status import MERGEABLE


def command(
    *number: Annotated[int, "PRの番号（--pr と同じ）"],
    pr: Annotated[int, "PRの番号（既定：今いる作業空間のPR）"] = 0,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """PRの状態：内容、レビュー・コメント、CIの結果、マージできるかを表示します。"""
    pr = optional_argument(number, pr, "--pr", json)

    def render(r):
        a = r.activity
        details = [f"  CI {c.name}：{c.conclusion or c.status}" for c in a.checks]
        details += [f"  レビュー {v.author}：{v.state}" + (f"：{v.body}" if v.body else "") for v in a.reviews]
        details += [f"  コメント {c.author}：{c.body}" for c in a.comments]
        return lines(
            f"PR #{r.number} {r.title}（{r.state}{'、下書き' if r.draft else ''}）{r.url}",
            f"  {r.head} → {r.base}" + (f"（Issue #{r.task}）" if r.task else "")
            + (f"  作成者：{r.author}" if r.author else ""),
            f"  マージ：{MERGEABLE.get(a.mergeable, '確認中')}" if r.state == "open" else None,
            "\n".join(details) or None,
        )

    return run_command("pr status", lambda inv: inv.module.pull_request_status(pr or None), render, json_output=json)
