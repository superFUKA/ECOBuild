from typing import Annotated

from .._output import run_command


def command(
    force: Annotated[bool, "強制的にpushする（--amend等の後。安全な方式で行う）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """作業空間のブランチをGitHubへpushします（作業空間でのみ）。"""

    def action(inv):
        return inv.module.require_workspace("push").push(force=force)

    return run_command("push", action, lambda r: f"pushしました：{r.branch} → {r.remote}", json_output=json)
