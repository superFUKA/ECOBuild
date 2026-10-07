from typing import Annotated

from ..._output import lines, optional_argument, run_command


def command(
    *number: Annotated[int, "消す作業空間のIssue番号（--issue と同じ）"],
    issue: Annotated[int, "消す作業空間のIssue番号（既定は今いる作業空間）"] = 0,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """手元の作業空間を消します。GitHubのブランチ・PR・Issueはそのままで、ecobuild task start でpushした所から再開できます。"""
    issue = optional_argument(number, issue, "--issue", json)

    def render(r):
        return lines(
            f"手元の作業空間 {r.branch} を消しました（作成元 {r.base}）",
            f"{r.switched_to} に移りました" if r.switched_to else None,
            f"再開：ecobuild task start {r.number}" + ("（GitHubのブランチから）" if r.remote else "（作成元の最新から）"),
        )

    return run_command("task remove", lambda inv: inv.module.remove_workspace(issue or None), render,
                       json_output=json)
