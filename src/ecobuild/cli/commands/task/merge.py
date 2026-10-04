from typing import Annotated

from ..._output import lines, run_command


def command(
    pr: Annotated[int, "マージするPRの番号（既定は今の作業空間のPR）"] = 0,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """作業空間のPRをsquashでマージし、Issueを閉じます（途中の反映なら作業空間を作り直します）。"""
    return run_command(
        "task merge",
        lambda inv: inv.module.pull_request(pr or None).merge(),
        lambda r: lines(
            f"PR #{r.number} をマージしました（{r.method}）",
            f"Issue #{r.closed_issue} を閉じました。ecobuild task clean で片付けられます" if r.closed_issue else None,
            "作業空間を作成元の最新から作り直しました" if r.workspace_rebuilt else None,
        ),
        json_output=json,
    )
