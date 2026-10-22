from typing import Annotated

from ..._output import lines, optional_argument, run_command
from ..workspace.close import leave, render_removed


def command(
    *number: Annotated[int, "片付けるタスクブランチのタスクの番号（--task と同じ。省略時：閉じたタスクのものすべて）"],
    task: Annotated[int, "片付けるタスクブランチのタスクの番号"] = 0,
    dry_run: Annotated[bool, "片付ける対象を表示するだけにする"] = False,
    yes: Annotated[bool, "確認せずに実行する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """手元のタスクブランチを片付けます。

    番号を省くと、閉じたタスクのタスクブランチをすべて片付けます（取り込んでいないコミットがあるものは残します）。
    番号を書くと、そのタスクブランチだけ：閉じたタスクなら片付け、開いているタスクなら手元の写しだけを消します
    （GitHubのブランチ・提出は残り、ecobuild task start でpushした所から再開できます）。タスクブランチを取り出していた
    作業空間も一緒に消えます。
    完了（task finish）したタスクブランチは自動で片付くので、普段は使いません。
    """
    task = optional_argument(number, task, "--task", json)

    def action(inv):
        module = inv.module
        if task:
            leave(module.root, inv)   # この作業空間を消すことがある
            return module.repository.prune_task_branch(task)
        preview = module.repository.prune_task_branches(dry_run=True)
        if dry_run or not preview.removed:
            return preview
        inv.confirm(f"タスクブランチ {', '.join(preview.removed)} を片付けますか？")
        leave(module.root, inv)
        return module.repository.prune_task_branches()

    def render(r):
        if hasattr(r, "remote"):   # 開いているタスクの手元の写しを消した
            return lines(
                f"{r.switched_to} に移りました" if r.switched_to else None,
                render_removed(r),
                f"手元のタスクブランチ {r.branch} を消しました（作成元 {r.base}）",
                f"再開：ecobuild task start {r.number}" + ("（GitHubのブランチから）" if r.remote else "（作成元の最新から）"),
            )
        if not r.removed:
            done = "片付けるタスクブランチはありません"
        else:
            done = ("片付ける対象：" if r.dry_run else "片付けました：") + ", ".join(r.removed)
        removed = "、".join(map(str, r.workspaces_removed))
        return lines(
            "\n".join(f"残しました：{s.branch}（{s.reason}）" for s in r.skipped) or None,
            f"{r.switched_to} に移りました" if r.switched_to else None,
            (f"消す作業空間：{removed}" if r.dry_run else f"作業空間 {removed} を消しました") if removed else None,
            done,
        )

    return run_command("task prune", action, render, json_output=json, yes=yes)
