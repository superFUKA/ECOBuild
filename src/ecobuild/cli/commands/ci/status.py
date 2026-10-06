from typing import Annotated

from ..._output import run_command


def command(
    pr: Annotated[int, "このPRのブランチのCI（既定：今いるブランチ）"] = 0,
    count: Annotated[int, "表示する件数"] = 5,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """CIの実行と結果を、新しい順に表示します。"""

    def render(r):
        return "\n".join(f"#{x.id} {x.created[:16].replace('T', ' ')} {x.workflow}（{x.event}）："
                         f"{x.conclusion or x.status}  {x.url}" for x in r) or "CIの実行はありません"

    return run_command("ci status", lambda inv: inv.module.ci_runs(pull_request=pr or None, limit=count), render,
                       json_output=json)
