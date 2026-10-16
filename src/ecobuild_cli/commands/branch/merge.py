from typing import Annotated

from ..._output import run_command


def command(
    name: Annotated[str, "取り込むブランチ（ecobuild branch submit で提出したもの）"],
    ignore_checks: Annotated[bool, "CIが失敗していても取り込む"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ブランチ同士の提出（ecobuild branch submit で作ったもの）を、マージコミットで取り込みます。"""
    return run_command("branch merge", lambda inv: inv.module.repository.merge_branch(name, ignore_checks=ignore_checks),
                       lambda r: f"{name} の提出を取り込みました（{r.method}）", json_output=json)
