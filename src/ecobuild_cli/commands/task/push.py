from typing import Annotated

from ..._output import run_command

AGENT = "owner"


def command(
    force: Annotated[bool, "強制的にpushする（--amend等の後。安全な方式で行う）"] = False,
    dry_run: Annotated[bool, "pushせずに、pushするコミットの一覧を表示する"] = False,
    pipelines: Annotated[bool, "push の前・後のパイプラインを走らせる（ecobuild pipeline。--no-pipelines で省く）"] = True,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスクブランチのブランチをGitHubへpushします（タスクブランチでのみ）。

    push の前・後に当てたパイプライン（ecobuild pipeline on）があれば走らせます。前のものが失敗したら push しません。
    """

    def action(inv):
        return inv.module.push(force=force, dry_run=dry_run, progress=inv.info, pipelines=pipelines)

    def render(r):
        listed = "\n".join(f"  {c}" for c in r.commits)
        if not r.pushed:
            return f"pushするコミット（{len(r.commits)}件）：{r.branch} → {r.remote}\n{listed}" if r.commits else "pushするコミットはありません"
        return f"pushしました：{r.branch} → {r.remote}" + (f"（{len(r.commits)}件）\n{listed}" if r.commits else "")

    return run_command("task push", action, render, json_output=json)
