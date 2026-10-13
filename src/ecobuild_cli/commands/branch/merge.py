from typing import Annotated

from ..._output import run_command


def command(
    pr: Annotated[int, "マージするPRの番号"],
    ignore_checks: Annotated[bool, "CIが失敗していてもマージする"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ブランチ同士のPRを、マージコミットでマージします。"""
    return run_command("branch merge", lambda inv: inv.module.pull_request(pr).merge(ignore_checks=ignore_checks),
                       lambda r: f"PR #{r.number} をマージしました（{r.method}）", json_output=json)
