from typing import Annotated

from ..._output import run_command


def command(
    title: Annotated[str, "Issueのタイトル"],
    body: Annotated[str, "Issueの本文"] = "",
    start: Annotated[bool, "続けて作業空間を作る"] = False,
    base: Annotated[str, "--start時の作成元のブランチ（既定はecobuild.tomlのdefault_base）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスク（GitHub Issue）を作成します。"""

    def action(inv):
        task = inv.module.create_task(title, body=body)
        workspace = task.start(base=base or None) if start else None
        return {"task": task, "workspace": workspace}

    def render(r):
        task, workspace = r["task"], r["workspace"]
        text = f"Issue #{task.number} を作成しました：{task.url}"
        return text + (f"\n作業空間 {workspace.branch} に切り替えました" if workspace else "")

    return run_command("task new", action, render, json_output=json)
