from typing import Annotated

from ecobuild import workspaces as _workspaces
from ..._output import run_command


def command(
    issue: Annotated[int, "Issueの番号"],
    name: Annotated[str, "タスクブランチの名前（task/<番号>-<名前>。新しく作るときは必須。日本語も使えます。例：ログイン画面）"] = "",
    base: Annotated[str, "作成元のブランチ（既定はecobuild.tomlのdefault_base。子タスクは親のタスクブランチに決まる）"] = "",
    dir: Annotated[str, "このディレクトリに新しい作業空間（clone）を作り、そこにタスクブランチを置く（並行作業用。例：../Calc-7）"] = "",
    ignore_blocked: Annotated[bool, "先に終わるべきタスクが開いていても始める"] = False,
    no_branch: Annotated[bool, "タスクブランチを作らずに作業中にする（調査・設計等、コードを変えないタスク）"] = False,
    take_over: Annotated[bool, "他の人が担当していても引き継いで始める（担当者を自分にし、タスクに残す）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """Issueのタスクブランチ（task/<番号>-<名前>）を作ってGitHubにも置き、切り替えます。

    新しく作るときは --name で名前を指定します（題名をそのまま使えます。空白や ~ ^ : ? * [ ] \\ / " < > | は使えません）。
    既にあれば切り替え、手元になければGitHubから再開します（--name は要りません）。

    新しく作るときは、親タスク（開いている子タスクがある）と、先に終わるべきタスクを待っているタスクでは止まります。
    他の人が担当しているタスクでも止まります（引き継ぐなら --take-over）。
    """

    def action(inv):
        if no_branch:
            return inv.module.repository.start_task_without_branch(issue, ignore_blocked=ignore_blocked, take_over=take_over)
        if not dir:
            return inv.module.repository.task(issue).start(base=base or None, name=name, ignore_blocked=ignore_blocked,
                                                           take_over=take_over)
        module = inv.module.start_task_in(issue, inv.cwd / dir, base=base or None, name=name,
                                          ignore_blocked=ignore_blocked, take_over=take_over)
        _workspaces.record_quietly(module.root)   # workspace list・task list で場所が分かるように
        inv.use_module(module)
        return module.repository.current_task_branch()

    def render(r):
        if no_branch:
            return f"#{r.number} {r.title} を作業中にしました（タスクブランチなし。終わったら ecobuild task close {r.number}）"
        where = f"（{r.root}）" if dir else ""
        return f"タスクブランチ {r.branch} に切り替えました（作成元 {r.base}）{where}"

    return run_command("task start", action, render, json_output=json)
