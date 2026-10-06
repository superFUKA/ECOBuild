from typing import Annotated

from ..._output import run_command


def command(
    run: Annotated[int, "実行の番号（既定：今いるブランチの最新の失敗した実行）"] = 0,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """失敗したCIの手順のログを表示します。"""

    def action(inv):
        run_id, log = inv.module.ci_failed_log(run or None)
        return {"run": run_id, "log": log}

    return run_command("ci logs", action, lambda r: f"#{r['run']} の失敗した手順：\n{r['log']}", json_output=json)
