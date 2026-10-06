from typing import Annotated

from ..._output import lines, run_command


def command(
    issue: Annotated[int, "やめる作業空間のIssue番号（既定は今いる作業空間）"] = 0,
    close: Annotated[bool, "Issueも「対応しない」として閉じる（既定は開いたまま。後で task start でやり直せる）"] = False,
    yes: Annotated[bool, "確認せずに実行する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """PRを出さずに作業をやめます。開いているPRを閉じ、作業空間を手元とGitHubから消し、作成元へ戻ります。"""

    def action(inv):
        module = inv.module
        preview = module.drop_workspace(issue or None, close=close, dry_run=True)
        if preview.lost_commits:
            inv.confirm(f"{preview.branch} の作成元に入っていないコミット {len(preview.lost_commits)} 件"
                        f"（{', '.join(preview.lost_commits)}）を捨てますか？")
        return module.drop_workspace(issue or None, close=close, discard=True)

    def render(r):
        return lines(
            f"作業空間 {r.branch} を捨てました" + (f"（コミット {len(r.lost_commits)} 件）" if r.lost_commits else ""),
            f"PR {', '.join(f'#{n}' for n in r.closed_pull_requests)} を閉じました" if r.closed_pull_requests else None,
            f"{r.switched_to} に移りました" if r.switched_to else None,
            f"Issue #{r.number} を「対応しない」として閉じました" if r.issue_closed
            else f"Issue #{r.number} は開いたままです（ecobuild task start {r.number} でやり直せます）",
        )

    return run_command("task drop", action, render, json_output=json, yes=yes)
