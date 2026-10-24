import sys
from typing import Annotated

from ecobuild.errors import EcoBuildError
from ecobuild_agent import rules as _rules
from ecobuild_agent.results import AgentTool

from ...._output import run_command


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """エージェントに渡せるツールの一覧（渡すツール〔tools〕を選ぶとき）を表示します。

    ECOBuild のコマンドのうちエージェントに許すもの（印：read・change・owner。owner はタスクの持ち主だけ）と、
    子のエージェントを扱うツール（children）です。モジュールの中では、その型のコマンドも入ります（外では、
    すべての型のコマンド：プリセットを直すとき）。
    """
    def action(inv):
        try:
            root = inv.module.root
        except EcoBuildError:       # モジュールの外
            root = None
        return [AgentTool(*t) for t in _rules.tool_list(root, (sys.executable, "-m", "ecobuild_cli"))]

    return run_command("agent registry tools", action,
                       lambda r: "\n".join(f"{t.name}（{t.mark}）：{t.summary}" for t in r), json_output=json)
