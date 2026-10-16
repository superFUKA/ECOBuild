from typing import Annotated

from ecobuild.errors import ErrorCode
from ecowork import WorkError
from ..._output import lines, run_command


def command(
    issue: Annotated[int, "タスクの番号"],
    not_planned: Annotated[bool, "「対応しない」として閉じる（既定は「完了」）"] = False,
    yes: Annotated[bool, "作業空間があっても、確認せずに作業を捨てて閉じる"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """タスク（Issue）を閉じます（コードを変えないタスク等）。

    作業空間に提出や取り込んでいないコミットがあれば、確かめてから作業を捨てて「対応しない」として閉じます
    （ecobuild task drop --close と同じ）。取り込むなら ecobuild task finish。
    """

    def action(inv):
        module = inv.module
        try:
            return module.repository.close_task(issue, not_planned=not_planned)
        except WorkError as error:
            if error.code != ErrorCode.UNFINISHED_WORK:
                raise
        preview = module.repository.drop_workspace(issue, close=True, dry_run=True)
        lost = f"（取り込んでいないコミット {len(preview.lost_commits)} 件を捨てます）" if preview.lost_commits else ""
        inv.confirm(f"#{issue} の作業空間 {preview.branch} の作業を捨てて、「対応しない」として閉じますか？{lost}")
        return module.repository.drop_workspace(issue, close=True, discard=True)

    def render(r):
        if hasattr(r, "lost_commits"):
            return lines(
                "開いていた提出を閉じました" if r.closed_pull_requests else None,
                f"{r.switched_to} に移りました" if r.switched_to else None,
                f"作業空間 {r.branch} を捨てて、#{r.number} を「対応しない」として閉じました",
            )
        return f"#{r.number} を閉じました"

    return run_command("task close", action, render, json_output=json, yes=yes)
