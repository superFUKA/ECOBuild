from typing import Annotated

from ..._output import run_command


def command(
    issue: Annotated[int, "Issueの番号"],
    base: Annotated[str, "作成元のブランチ（既定はecobuild.tomlのdefault_base）"] = "",
    dir: Annotated[str, "作業空間を、このディレクトリへの専用のcloneで作る（並行作業用。例：../Calc-7）"] = "",
    ignore_blocked: Annotated[bool, "先に終わるべきタスクが開いていても始める"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """Issueの作業空間（task/<番号>）を作ってGitHubにも置き、切り替えます。既にあれば切り替え、手元になければGitHubから再開します。

    新しく作るときは、親タスク（開いている子タスクがある）と、先に終わるべきタスクを待っているタスクでは止まります。
    """

    def action(inv):
        if not dir:
            return inv.module.task(issue).start(base=base or None, ignore_blocked=ignore_blocked)
        module = inv.module.start_task_in(issue, inv.cwd / dir, base=base or None, ignore_blocked=ignore_blocked)
        inv.use_module(module)
        return module.current_workspace()

    def render(r):
        where = f"（{inv_root(r)}）" if dir else ""
        return f"作業空間 {r.branch} に切り替えました（作成元 {r.base}）{where}"

    return run_command("task start", action, render, json_output=json)


def inv_root(workspace) -> str:
    return str(workspace._repository.root)
