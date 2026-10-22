from typing import Annotated

from ..._output import lines, optional_argument, run_command
from ..workspace.close import leave, render_removed


def command(
    *number: Annotated[int, "やめるタスクブランチのIssue番号（--issue と同じ）"],
    issue: Annotated[int, "やめるタスクブランチのIssue番号（既定は今いるタスクブランチ）"] = 0,
    close: Annotated[bool, "Issueも「対応しない」として閉じる（既定は開いたまま。後で task start でやり直せる）"] = False,
    yes: Annotated[bool, "確認せずに実行する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """作業をやめます（取り込まずに、タスクブランチを手元とGitHubから消します）。

    開いている提出を閉じ、タスクブランチを取り出していた作業空間と一緒に消します。タスクは開いたまま（--close で
    「対応しない」として閉じる）。
    """

    issue = optional_argument(number, issue, "--issue", json)

    def action(inv):
        module = inv.module
        preview = module.repository.drop_task(issue or None, close=close, dry_run=True)
        if preview.lost_commits:
            inv.confirm(f"{preview.branch} の作成元に入っていないコミット {len(preview.lost_commits)} 件"
                        f"（{', '.join(preview.lost_commits)}）を捨てますか？")
        leave(module.root, inv)   # この作業空間を消すことがある
        return module.repository.drop_task(issue or None, close=close, discard=True)

    def render(r):
        return lines(
            f"タスクブランチ {r.branch} を捨てました" + (f"（コミット {len(r.lost_commits)} 件）" if r.lost_commits else ""),
            "開いていた提出を閉じました" if r.closed_pull_requests else None,
            f"{r.switched_to} に移りました" if r.switched_to else None,
            render_removed(r),
            f"Issue #{r.number} を「対応しない」として閉じました" if r.issue_closed
            else f"Issue #{r.number} は開いたままです（ecobuild task start {r.number} でやり直せます）" if r.issue_open
            else f"Issue #{r.number} は閉じています（段階はそのままです）",
        )

    return run_command("task drop", action, render, json_output=json, yes=yes)
