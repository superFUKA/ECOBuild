from typing import Annotated

from ..._output import run_command


def command(
    issue: Annotated[int, "Issueの番号"],
    name: Annotated[str, "タスクブランチの名前（task/<番号>-<名前>。新しく作るときは必須。日本語も使えます。例：ログイン画面）"] = "",
    base: Annotated[str, "作成元のブランチ（既定はecobuild.tomlのdefault_base。子タスクは親のタスクブランチに決まる）"] = "",
    account: Annotated[str, "作業空間で使う GitHub のアカウント（AI 用のアカウント等。担当者もそのアカウント）"] = "",
    ignore_blocked: Annotated[bool, "先に終わるべきタスクが開いていても始める"] = False,
    no_branch: Annotated[bool, "タスクブランチを作らずに作業中にする（調査・設計等、コードを変えないタスク）"] = False,
    take_over: Annotated[bool, "他の人が担当していても引き継いで始める（担当者を自分にし、タスクに残す）"] = False,
    pipelines: Annotated[bool, "タスクの開始の後のパイプラインを走らせる（ecobuild pipeline。--no-pipelines で省く）"] = True,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """Issueのタスクブランチ（task/<番号>-<名前>）を作ってGitHubにも置き、作業空間に取り出します。

    作業空間は元の clone の中の .ecobuild/w/<番号>（git worktree）です。元の clone のブランチは変わりません。
    作業はその作業空間で行い、task finish・drop・close で作業空間ごと片付きます。
    新しく作るときは --name で名前を指定します（題名をそのまま使えます。空白や ~ ^ : ? * [ ] \\ / " < > | は使えません）。
    既に作業空間があればそこを返し、手元になければGitHubから再開します（--name は要りません）。

    新しく作るときは、親タスク（開いている子タスクがある）と、先に終わるべきタスクを待っているタスクでは止まります。
    他の人が担当しているタスクでも止まります（引き継ぐなら --take-over）。
    """

    def action(inv):
        if no_branch:
            return inv.module.repository.start_task_without_branch(issue, ignore_blocked=ignore_blocked, take_over=take_over)
        module = inv.module.start_task(issue, base=base or None, name=name, ignore_blocked=ignore_blocked,
                                       take_over=take_over, account=account or None, progress=inv.info,
                                       pipelines=pipelines)
        inv.use_module(module)
        return started(module)

    def render(r):
        if no_branch:
            return f"#{r.number} {r.title} を作業中にしました（タスクブランチなし。終わったら ecobuild task close {r.number}）"
        return render_started(r)

    return run_command("task start", action, render, json_output=json)


def started(module) -> dict:
    """始めたタスクブランチと、取り出した作業空間（task start・task new --start の結果）。"""
    task_branch = module.repository.current_task_branch()
    return {"number": task_branch.number, "branch": task_branch.branch, "base": task_branch.base,
            "workspace": module.root.as_posix()}


def render_started(r) -> str:
    return f"タスクブランチ {r['branch']}（作成元 {r['base']}）を作業空間 {r['workspace']} に置きました"
