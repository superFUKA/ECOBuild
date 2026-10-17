from typing import Annotated

from ..._output import run_command, split_list, split_numbers


def command(
    title: Annotated[str, "Issueのタイトル"],
    body: Annotated[str, "Issueの本文"] = "",
    label: Annotated[str, "ラベル（カンマ区切り。なければ作る）"] = "",
    assignee: Annotated[str, "担当者（カンマ区切り。@me は自分。--start なら省略時は自分）"] = "",
    parent: Annotated[int, "親タスクの番号（このタスクを子タスクにする）"] = 0,
    blocked_by: Annotated[str, "先に終わるべきタスクの番号（カンマ区切り。それが閉じるまで task start で止まる）"] = "",
    milestone: Annotated[str, "マイルストーンの題名（ecobuild milestone list で一覧）"] = "",
    due: Annotated[str, "期限（YYYY-MM-DD）"] = "",
    planned_start: Annotated[str, "開始予定日（YYYY-MM-DD）"] = "",
    planned_end: Annotated[str, "終了予定日（YYYY-MM-DD）"] = "",
    start: Annotated[bool, "続けてタスクブランチを作る"] = False,
    base: Annotated[str, "--start時の作成元のブランチ（既定はecobuild.tomlのdefault_base。子タスクは親のタスクブランチに決まる）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスク（GitHub Issue）を作成します。"""
    blockers = split_numbers(blocked_by, "--blocked-by", json)

    def action(inv):
        task = inv.module.repository.create_task(title, body=body, labels=split_list(label), assignees=split_list(assignee),
                                      parent=parent or None, blocked_by=blockers, milestone=milestone or None,
                                      plan={"due": due or None, "planned_start": planned_start or None,
                                            "planned_end": planned_end or None})
        task_branch = task.start(base=base or None) if start else None
        return {"task": task, "task_branch": task_branch}

    def render(r):
        task, task_branch = r["task"], r["task_branch"]
        text = f"Issue #{task.number} を作成しました：{task.url}"
        return text + (f"\nタスクブランチ {task_branch.branch} に切り替えました" if task_branch else "")

    return run_command("task new", action, render, json_output=json)
