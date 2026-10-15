from typing import Annotated

from ..._output import missing, optional_argument, run_command


def command(
    *number: Annotated[int, "取り消す、完了したタスクの番号（--task と同じ）"],
    task: Annotated[int, "取り消す、完了したタスクの番号"] = 0,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """完了したタスクの取り込み（中間提出も含む）を取り消すタスクと作業空間を作ります（取り消しのコミットまで）。

    確かめてから ecobuild task submit → task finish で反映します。
    """
    task = optional_argument(number, task, "--task", json)
    if not task:
        return missing("タスクの番号", json)
    return run_command(
        "task revert", lambda inv: inv.module.revert_task(task),
        lambda r: f"#{r.reverted_task} を取り消すコミットを作りました：作業空間 {r.branch}（タスク #{r.task}）\n"
                  "次：確かめてから ecobuild task submit → ecobuild task finish", json_output=json)
