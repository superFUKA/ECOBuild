from typing import Annotated

from ..._output import run_command


def command(
    number: Annotated[int, "PRの番号"],
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """閉じたPRを開き直します。"""
    return run_command("pr reopen", lambda inv: inv.module.reopen_pull_request(number),
                       lambda r: f"PR #{r.number} を開き直しました：{r.url}", json_output=json)
