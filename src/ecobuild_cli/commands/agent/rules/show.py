import sys
from typing import Annotated

from ecobuild_agent import rules as _rules

from ...._output import run_command
from . import _render


def command(tools: Annotated[bool, "エージェントに渡せるツールの一覧も出す（使わせないものを選ぶとき。数秒かかります）"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """モジュールのエージェント向けの決まり：全エージェント共通の文、登録ごとの文と使わせないツールを表示します。

    表示するのは今いる作業空間（作業ツリー）のものです。起動したエージェントに効くのは作成元のブランチに取り込まれた
    もので、違えば「まだ効いていない」と出します。
    """
    def action(inv):
        return _rules.view(inv.module.root, program=(sys.executable, "-m", "ecobuild_cli") if tools else None)

    return run_command("agent rules show", action, _render.details, json_output=json)
