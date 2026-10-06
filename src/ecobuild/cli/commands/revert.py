from typing import Annotated

from .._output import missing, run_command


def command(
    pr: Annotated[int, "取り消すマージ済みのPRの番号"] = 0,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """マージ済みのPRを取り消す作業空間を作ります（Issue作成→取り消しのコミット）。ecobuild task submit でPRを出します。"""
    if not pr:
        return missing("--pr")
    return run_command(
        "revert", lambda inv: inv.module.revert(pr),
        lambda r: f"PR #{r.pull_request} を取り消すコミットを作りました：作業空間 {r.branch}（Issue #{r.task}）。"
                  "確かめてから ecobuild task submit", json_output=json)
