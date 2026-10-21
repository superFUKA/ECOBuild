from typing import Annotated

from ecobuild_agent import team as _team

from ..._output import run_command
from .team import _forward


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業役が、報告（.ecobuild/ai/report.md）を作った上の役（管理役）に知らせます。

    報告を書き終えたとき・報告だけの仕事（--report-only）を終えたときに使います。上の役の受け箱に報告の頭を入れ、
    agent team list に「報告済み」と出ます（report_told・report_read：上の役に届いたか）。コンテナの中からは係に頼みます。
    """
    return run_command("agent report",
                       lambda inv: _forward.run(inv, ["agent", "report"], lambda inv: _team.report(inv.module.root)),
                       lambda r: f"報告を知らせました（{r.get('report')}）。", json_output=json)
