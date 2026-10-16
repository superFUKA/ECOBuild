from typing import Annotated

from ..._output import lines, optional_argument, run_command


def command(
    *number: Annotated[int, "片付ける作業空間のタスクの番号（--task と同じ。省略時：閉じたタスクのものすべて）"],
    task: Annotated[int, "片付ける作業空間のタスクの番号"] = 0,
    dry_run: Annotated[bool, "片付ける対象を表示するだけにする"] = False,
    yes: Annotated[bool, "確認せずに実行する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """手元の作業空間を片付けます。

    番号を省くと、閉じたタスクの作業空間をすべて片付けます（取り込んでいないコミットがあるものは残します）。
    番号を書くと、その作業空間だけ：閉じたタスクなら片付け、開いているタスクなら手元の写しだけを消します
    （GitHubのブランチ・提出は残り、ecobuild task start でpushした所から再開できます）。
    完了（task finish）した作業空間は自動で片付くので、普段は使いません。
    """
    task = optional_argument(number, task, "--task", json)

    def action(inv):
        module = inv.module
        if task:
            return module.repository.clean_workspace(task)
        preview = module.repository.clean_workspaces(dry_run=True)
        if dry_run or not preview.removed:
            return preview
        inv.confirm(f"作業空間 {', '.join(preview.removed)} を片付けますか？")
        return module.repository.clean_workspaces()

    def render(r):
        if hasattr(r, "remote"):   # 開いているタスクの手元の写しを消した
            return lines(
                f"{r.switched_to} に移りました" if r.switched_to else None,
                f"手元の作業空間 {r.branch} を消しました（作成元 {r.base}）",
                f"再開：ecobuild task start {r.number}" + ("（GitHubのブランチから）" if r.remote else "（作成元の最新から）"),
            )
        if not r.removed:
            done = "片付ける作業空間はありません"
        else:
            done = ("片付ける対象：" if r.dry_run else "片付けました：") + ", ".join(r.removed)
        return lines(
            "\n".join(f"残しました：{s.branch}（{s.reason}）" for s in r.skipped) or None,
            f"{r.switched_to} に移りました" if r.switched_to else None,
            done,
        )

    return run_command("task prune", action, render, json_output=json, yes=yes)
