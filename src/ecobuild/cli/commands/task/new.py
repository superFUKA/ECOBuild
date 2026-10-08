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
    start: Annotated[bool, "続けて作業空間を作る"] = False,
    base: Annotated[str, "--start時の作成元のブランチ（既定はecobuild.tomlのdefault_base）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスク（GitHub Issue）を作成します。"""
    blockers = split_numbers(blocked_by, "--blocked-by", json)

    def action(inv):
        task = inv.module.create_task(title, body=body, labels=split_list(label), assignees=split_list(assignee),
                                      parent=parent or None, blocked_by=blockers, milestone=milestone or None)
        workspace = task.start(base=base or None) if start else None
        return {"task": task, "workspace": workspace}

    def render(r):
        task, workspace = r["task"], r["workspace"]
        text = f"Issue #{task.number} を作成しました：{task.url}"
        return text + (f"\n作業空間 {workspace.branch} に切り替えました" if workspace else "")

    return run_command("task new", action, render, json_output=json)
