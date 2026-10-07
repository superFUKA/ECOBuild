from typing import Annotated

from ..._output import lines, optional_argument, run_command

MERGEABLE = {"CONFLICTING": "衝突あり（ecobuild sync で解決）", "MERGEABLE": "可能"}


def command(
    *number: Annotated[int, "Issueの番号（--issue と同じ）"],
    issue: Annotated[int, "Issueの番号（既定：今いる作業空間）"] = 0,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスクの状態：Issue、作業空間、PRのレビュー・コメント・CIの結果を表示します。"""

    issue = optional_argument(number, issue, "--issue", json)

    def render(r):
        a = r.activity
        details = []
        if a is not None:
            details += [f"  CI {c.name}：{c.conclusion or c.status}" for c in a.checks]
            details += [f"  レビュー {v.author}：{v.state}" + (f"：{v.body}" if v.body else "") for v in a.reviews]
            details += [f"  コメント {c.author}：{c.body}" for c in a.comments]
        opened = r.pull_request is not None and r.pull_request.state == "open"
        return lines(
            f"#{r.number} {r.title}（{'開いています' if r.state == 'open' else '閉じています'}）{r.url}",
            f"作業空間：task/{r.number}（作成元 {r.base}）" if r.workspace else "作業空間：手元になし",
            f"PR #{r.pull_request.number}（{r.pull_request.state}）{r.pull_request.url}" if r.pull_request
            else "PR：なし",
            f"  マージ：{MERGEABLE.get(a.mergeable, '確認中')}" if a is not None and opened else None,
            "\n".join(details) or None,
        )

    return run_command("task status", lambda inv: inv.module.task_status(issue or None), render, json_output=json)
