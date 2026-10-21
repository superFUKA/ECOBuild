from typing import Annotated

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_agent import team as _team

from ...._output import run_command, to_data
from . import _forward


def command(name: Annotated[str, "宛先：チームの1人の名前（か子タスクの番号）。lead なら上の役（管理役が進行役へ要約・質問を送る）"],
            text: Annotated[str, "伝えること"],
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業役・管理役に言付けを送ります（進行役→管理役の命令、管理役→作業役の指示、管理役→進行役 lead の要約）。

    作業役の受け箱に入れ、作業役を動かしている側（GUI の窓等）が届けます。作業中でも、返答を止めずに次の区切りで
    届きます（任せた仕事を途中で直したいときに使えます）。
    """
    def action(inv):
        if not text.strip():
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "伝えることが空です。")
        return _forward.run(inv, ["agent", "team", "send", name, text],
                            lambda inv: to_data(_team.send(inv.module.root, name, text)))

    return run_command("agent team send", action, lambda r: f"「{r.get('name')}」に送りました。", json_output=json)
