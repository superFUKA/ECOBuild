from datetime import datetime
from typing import Annotated

from ..._output import optional_argument, run_command


def command(
    *number: Annotated[int, "PRの番号（--pr と同じ）"],
    pr: Annotated[int, "このPRのブランチのCI（既定：今いるブランチ）"] = 0,
    count: Annotated[int, "表示する件数"] = 5,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """CIの実行と結果を、新しい順に表示します。"""

    pr = optional_argument(number, pr, "--pr", json)

    def render(r):
        return "\n".join(f"#{x.id} {_local(x.created)} {x.workflow}（{x.event}）："
                         f"{x.conclusion or x.status}  {x.url}" for x in r) or "CIの実行はありません"

    return run_command("ci status", lambda inv: inv.module.ci_runs(pull_request=pr or None, limit=count), render,
                       json_output=json)


def _local(timestamp: str) -> str:
    """GitHubの時刻（UTC）を、このPCの時刻で表示する。"""
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return timestamp[:16]
