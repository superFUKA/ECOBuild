from typing import Annotated

from ecowork import model as _work

from ..._output import run_command, split_list, split_numbers
from .start import render_started, started


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
    start: Annotated[bool, "続けてタスクブランチを作り、作業空間に取り出す（task start と同じ。--name が必要）"] = False,
    name: Annotated[str, "--start時のタスクブランチの名前（task/<番号>-<名前>。日本語も使えます。題名をそのまま使うなら同じ文字列）"] = "",
    base: Annotated[str, "--start時の作成元のブランチ（既定はecobuild.tomlのdefault_base。子タスクは親のタスクブランチに決まる）"] = "",
    pipelines: Annotated[bool, "--start時、タスクの開始の後のパイプラインを走らせる（ecobuild pipeline。--no-pipelines で省く）"] = True,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスク（GitHub Issue）を作成します。"""
    blockers = split_numbers(blocked_by, "--blocked-by", json)

    def action(inv):
        if start:
            _work.check_branch_label(name)   # Issueを作る前に確かめる
        task = inv.module.repository.create_task(title, body=body, labels=split_list(label), assignees=split_list(assignee),
                                      parent=parent or None, blocked_by=blockers, milestone=milestone or None,
                                      plan={"due": due or None, "planned_start": planned_start or None,
                                            "planned_end": planned_end or None})
        if not start:
            return {"task": task, "task_branch": None}
        module = inv.module.start_task(task.number, base=base or None, name=name, progress=inv.info,
                                       pipelines=pipelines)
        inv.use_module(module)
        return {"task": task, "task_branch": started(module)}

    def render(r):
        task, task_branch = r["task"], r["task_branch"]
        text = f"Issue #{task.number} を作成しました：{task.url}"
        return text + ("\n" + render_started(task_branch) if task_branch else "")

    return run_command("task new", action, render, json_output=json)
