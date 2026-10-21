from typing import Annotated

from ..._output import run_command


def command(
    task: Annotated[int, "タスクの作業空間の場所（task start --new-workspace が作る所）。省くと workspace create が作る所"] = 0,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """新しい作業空間の既定の場所を表示します。

    <置き場所>/<モジュール名>/<番号> です。置き場所は ecobuild config の workspace_directory（既定：モジュールの親の workspace）。
    """

    def action(inv):
        return {"path": inv.module.new_workspace_path(task or None).as_posix()}

    return run_command("workspace path", action, lambda r: r["path"], json_output=json)
