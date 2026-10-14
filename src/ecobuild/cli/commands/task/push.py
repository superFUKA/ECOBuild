from typing import Annotated

from ..._output import run_command


def command(
    force: Annotated[bool, "強制的にpushする（--amend等の後。安全な方式で行う）"] = False,
    dry_run: Annotated[bool, "pushせずに、pushするコミットの一覧を表示する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """作業空間のブランチをGitHubへpushします（作業空間でのみ）。"""

    def action(inv):
        return inv.module.require_workspace("push").push(force=force, dry_run=dry_run)

    def render(r):
        listed = "\n".join(f"  {c}" for c in r.commits)
        if not r.pushed:
            return f"pushするコミット（{len(r.commits)}件）：{r.branch} → {r.remote}\n{listed}" if r.commits else "pushするコミットはありません"
        return f"pushしました：{r.branch} → {r.remote}" + (f"（{len(r.commits)}件）\n{listed}" if r.commits else "")

    return run_command("task push", action, render, json_output=json)
