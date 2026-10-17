from typing import Annotated

from ..._output import optional_argument, run_command


def command(
    *number: Annotated[int, "タスクの番号（--task と同じ）"],
    task: Annotated[int, "タスクの番号（既定は今いるタスクブランチ）"] = 0,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスクの提出の差分を表示します（提出がなければ、タスクブランチの作成元との差分）。"""
    task = optional_argument(number, task, "--task", json)
    return run_command("task diff", lambda inv: inv.module.repository.task_diff(task or None),
                       lambda r: r or "差分はありません", json_output=json)
