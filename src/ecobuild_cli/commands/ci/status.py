from typing import Annotated

from ..._output import local_time, optional_argument, run_command


def command(
    *number: Annotated[int, "タスクの番号（--task と同じ）"],
    task: Annotated[int, "このタスクのタスクブランチのCI（既定：今いるブランチ）"] = 0,
    count: Annotated[int, "表示する件数"] = 5,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """CIの実行と結果を、新しい順に表示します。"""

    task = optional_argument(number, task, "--task", json)

    def render(r):
        return "\n".join(f"#{x.id} {_local(x.created)} {x.workflow}（{x.event}）："
                         f"{x.conclusion or x.status}  {x.url}" for x in r) or "CIの実行はありません"

    return run_command("ci status", lambda inv: inv.module.repository.ci_runs(limit=count, task=task or None), render,
                       json_output=json)


def _local(timestamp: str) -> str:
    return local_time(timestamp, "%Y-%m-%d %H:%M")
