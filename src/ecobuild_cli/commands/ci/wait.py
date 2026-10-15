from typing import Annotated

from ..._output import optional_argument, run_command


def command(
    *number: Annotated[int, "タスクの番号（--task と同じ）"],
    task: Annotated[int, "このタスクの作業空間（提出）のCIを待つ（既定：今いるブランチ）"] = 0,
    timeout: Annotated[int, "待つ時間の上限（秒）"] = 1800,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """GitHubにある最新のコミットのCIが終わるまで待ちます。失敗したら終了コード1（ecobuild ci logs でログ）。

    完了の前に待つなら、ecobuild task finish が待ちます。
    """
    task = optional_argument(number, task, "--task", json)

    def action(inv):
        inv.info("CIの結果を待っています…")
        return inv.module.ci_wait(timeout=timeout, task=task or None)

    return run_command("ci wait", action,
                       lambda r: "\n".join(f"#{x.id} {x.workflow}：{x.conclusion}  {x.url}" for x in r),
                       json_output=json)
