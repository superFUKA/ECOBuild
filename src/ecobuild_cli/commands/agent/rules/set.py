import sys
from typing import Annotated

from ecobuild_agent import rules as _rules

from ...._output import run_command
from .. import _change
from . import _render


def command(common: Annotated[str, "全エージェント共通の文（空なら消す。- なら標準入力から読む）"],
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """全エージェント共通の文を変えて、タスクブランチでコミットします（.ecobuild/agents/common.md）。

    起動したエージェントに効くのは、提出して作成元のブランチに取り込まれてからです。

    例：
      ecobuild agent rules set "前後がつながった段階（調べる→設計→実装）は分けず、自分で進める"
    """
    def action(inv):
        text = sys.stdin.read() if common == "-" else common
        changed, sha = _change.in_task_branch(inv, "エージェントの共通の文を変える",
                                              lambda module: _rules.write(module.root, text))
        return _render.view(inv.module.root, changed=tuple(changed), committed=sha)

    return run_command("agent rules set", action, _render.details, json_output=json)
