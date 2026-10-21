from typing import Annotated

from ecobuild import workspaces as _workspaces
from ..._output import run_command, usage_error


def command(
    issue: Annotated[int, "Issueの番号"],
    name: Annotated[str, "タスクブランチの名前（task/<番号>-<名前>。新しく作るときは必須。日本語も使えます。例：ログイン画面）"] = "",
    base: Annotated[str, "作成元のブランチ（既定はecobuild.tomlのdefault_base。子タスクは親のタスクブランチに決まる）"] = "",
    dir: Annotated[str, "このディレクトリに新しい作業空間（clone）を作り、そこにタスクブランチを置く（並行作業用。省くときは --new-workspace で既定の場所）"] = "",
    new_workspace: Annotated[bool, "既定の場所（ecobuild workspace path --task <番号>）に新しい作業空間を作り、そこにタスクブランチを置く"] = False,
    account: Annotated[str, "--dir の新しい作業空間で使う GitHub のアカウント（AI 用のアカウント等。担当者もそのアカウント）"] = "",
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

    if dir and new_workspace:
        return usage_error("--dir と --new-workspace は、どちらか1つを指定します。", json)
    if account and not (dir or new_workspace):
        return usage_error("--account は --dir（新しい作業空間）と一緒に指定します（今の作業空間は ecobuild account use）。", json)

    def action(inv):
        if no_branch:
            return inv.module.repository.start_task_without_branch(issue, ignore_blocked=ignore_blocked, take_over=take_over)
        if not (dir or new_workspace):
            return inv.module.repository.task(issue).start(base=base or None, name=name, ignore_blocked=ignore_blocked,
                                                           take_over=take_over)
        target = inv.cwd / dir if dir else inv.module.new_workspace_path(issue)
        module = inv.module.start_task_in(issue, target, base=base or None, name=name,
                                          ignore_blocked=ignore_blocked, take_over=take_over, account=account or None)
        _workspaces.record_quietly(module.root)   # workspace list・task list で場所が分かるように
        inv.use_module(module)
        return module.repository.current_task_branch()

    def render(r):
        if no_branch:
            return f"#{r.number} {r.title} を作業中にしました（タスクブランチなし。終わったら ecobuild task close {r.number}）"
        where = f"（{r.root}）" if dir else ""
        return f"タスクブランチ {r.branch} に切り替えました（作成元 {r.base}）{where}"

    return run_command("task start", action, render, json_output=json)
