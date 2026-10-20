from typing import Annotated

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_agent import team as _team

from ...._output import run_command, to_data
from . import _forward


def command(name: Annotated[str, "作業役の名前（か子タスクの番号）"],
            text: Annotated[str, "伝えること"],
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業役に言付けを送ります。

    作業役の受け箱に入れ、作業役を動かしている側（GUI の窓等）が、作業役が待機中になったときに届けます。
    """
    def action(inv):
        if not text.strip():
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "伝えることが空です。")
        return _forward.run(inv, ["agent", "team", "send", name, text],
                            lambda inv: to_data(_team.send(inv.module.root, name, text)))

    return run_command("agent team send", action, lambda r: f"作業役「{r.get('name')}」に送りました。", json_output=json)
