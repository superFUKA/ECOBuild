from typing import Annotated

from ..._output import optional_argument, run_command


def command(
    *number: Annotated[int, "実行の番号（--run と同じ）"],
    run: Annotated[int, "実行の番号（既定：今いるブランチの最新の実行）"] = 0,
    failed: Annotated[bool, "失敗したジョブだけをもう一度実行する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """CIをもう一度実行します（結果は ecobuild ci status で確認）。"""
    run = optional_argument(number, run, "--run", json)
    return run_command("ci rerun", lambda inv: {"run": inv.module.ci_rerun(run or None, failed_only=failed)},
                       lambda r: f"#{r['run']} をもう一度実行しました（ecobuild ci status で確認）", json_output=json)
