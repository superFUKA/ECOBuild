from typing import Annotated

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_bundle import team as _team

from ...._output import run_command
from . import _forward


def command(name: Annotated[str, "作業役の名前（か子タスクの番号）"],
            text: Annotated[str, "伝えること"],
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業役に言付けを送ります（GUI が届けます）。

    GUI がその作業役の会話に届けます。GUI のエージェントの窓の中の進行役から使います。
    """
    def action(inv):
        if not text.strip():
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "伝えることが空です。")
        return _forward.run(inv, ["agent", "team", "send", name, text], lambda inv: _without_window(inv))

    def _without_window(inv):
        _team.find(inv.module.root, name)   # 名前の誤りを先に知らせる
        raise EcoBuildError(ErrorCode.AGENT_ERROR, "言付けは、GUI のエージェントの窓の中の進行役からだけ送れます（届けるのは GUI）。",
                            hint=f"作業役の画面に直接書くか、作業役の {_team.BRIEF_FILE} を書き足してください。")

    return run_command("agent team send", action, lambda r: f"作業役「{r.get('name')}」に送りました。", json_output=json)
