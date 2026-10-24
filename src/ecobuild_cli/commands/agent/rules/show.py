from typing import Annotated

from ...._output import run_command
from . import _render


def command(json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """全エージェント共通の文（このモジュールで起動するどのエージェントにも渡す文）を表示します。

    表示するのは今いる作業空間（作業ツリー）のものです。起動したエージェントに効くのは作成元のブランチに取り込まれた
    もので、違えば「まだ効いていない」と出します。役ごとの文は、登録の文書（ecobuild agent registry）です。
    """
    return run_command("agent rules show", lambda inv: _render.view(inv.module.root), _render.details, json_output=json)
