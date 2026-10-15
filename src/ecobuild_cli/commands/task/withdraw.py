from typing import Annotated

from ..._output import lines, optional_argument, run_command


def command(
    *number: Annotated[int, "提出を取り下げるタスクの番号（--task と同じ）"],
    task: Annotated[int, "提出を取り下げるタスクの番号（既定は今いる作業空間）"] = 0,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """提出を取り下げて、作業中に戻します（作業空間はそのまま。もう一度 task submit で出し直せます）。

    作業そのものをやめるなら ecobuild task drop。
    """
    task = optional_argument(number, task, "--task", json)

    def render(r):
        number = r.head.removeprefix("task/")
        return lines(f"#{number} の提出を取り下げました（作業中に戻しました）",
                     f"次：直して ecobuild task submit で出し直す（やめるなら ecobuild task drop {number}）")

    return run_command("task withdraw", lambda inv: inv.module.withdraw(task or None), render, json_output=json)
