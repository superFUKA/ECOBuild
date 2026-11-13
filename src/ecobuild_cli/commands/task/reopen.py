from typing import Annotated

from ..._output import run_command
from ._show import STAGE_NAMES


def command(
    issue: Annotated[int, "Issueの番号"],
    stage: Annotated[str, "開き直した後の、作業を始める前の段階（planned：計画中、todo：未着手）"] = "",
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """閉じたタスク（Issue）を開き直します。続きは ecobuild task start でタスクブランチを作ります。

    --stage で、開き直したタスクを計画中（planned）か未着手（todo）にします（ecobuild task edit --stage と同じ）。
    """

    def action(inv):
        repository = inv.module.repository
        task = repository.reopen_task(issue)
        if stage:
            repository.plan_task(issue, stage=stage)
            task = repository.task(issue)
        return task

    def render(r):
        stage_name = STAGE_NAMES.get(stage, "")
        return f"#{r.number} を開き直しました" + (f"〈{stage_name}〉" if stage_name else "")

    return run_command("task reopen", action, render, json_output=json)
