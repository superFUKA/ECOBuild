from typing import Annotated

from ..._output import run_command, split_list


def command(
    title: Annotated[str, "Issueのタイトル"],
    body: Annotated[str, "Issueの本文"] = "",
    label: Annotated[str, "ラベル（カンマ区切り。なければ作る）"] = "",
    assignee: Annotated[str, "担当者（カンマ区切り。@me は自分。--start なら省略時は自分）"] = "",
    start: Annotated[bool, "続けて作業空間を作る"] = False,
    base: Annotated[str, "--start時の作成元のブランチ（既定はecobuild.tomlのdefault_base）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスク（GitHub Issue）を作成します。"""

    def action(inv):
        task = inv.module.create_task(title, body=body, labels=split_list(label), assignees=split_list(assignee))
        workspace = task.start(base=base or None) if start else None
        return {"task": task, "workspace": workspace}

    def render(r):
        task, workspace = r["task"], r["workspace"]
        text = f"Issue #{task.number} を作成しました：{task.url}"
        return text + (f"\n作業空間 {workspace.branch} に切り替えました" if workspace else "")

    return run_command("task new", action, render, json_output=json)
