from typing import Annotated

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_agent import team as _team

from ...._output import run_command, to_data
from . import _forward


def command(name: Annotated[str, "宛先：チームの1人の名前（か子タスクの番号）。lead なら上の役（管理役が進行役へ要約・質問を送る）"],
            *text: Annotated[str, "伝えること（--cancel なら要らない）"],
            cancel: Annotated[str, "まだ届いていない言付け（この番号）を取り消す"] = "",
            replace: Annotated[str, "まだ届いていない言付け（この番号）を取り消して、代わりに伝えることを送る"] = "",
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業役・管理役に言付けを送ります（進行役→管理役の命令、管理役→作業役の指示、管理役→進行役 lead の要約）。

    作業役の受け箱に入れ、作業役を動かしている側（GUI の窓等）が届けます。作業中でも、返答を止めずに次の区切りで
    届きます（任せた仕事を途中で直したいときに使えます）。結果の message_id が言付けの番号で、届いたかは
    agent team list --json の messages で分かります。まだ届いていなければ --cancel・--replace で取り消せます。
    """
    words = " ".join(text)

    def action(inv):
        if cancel and replace:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "--cancel と --replace は一緒に使えません。")
        if not cancel and not words.strip():
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "伝えることが空です。")
        args = ["agent", "team", "send", name, *([words] if words else []), *(["--cancel", cancel] if cancel else []),
                *(["--replace", replace] if replace else [])]
        return _forward.run(inv, args, lambda inv: to_data(_send(inv.module.root)))

    def _send(root):
        if cancel:
            return _team.cancel(root, name, cancel)
        if replace:
            _team.cancel(root, name, replace)
        return _team.send(root, name, words)

    return run_command("agent team send", action, _render(cancel), json_output=json)


def _render(cancel: str):
    def render(r) -> str:
        if cancel:
            return f"「{r.get('name')}」への言付け {r.get('message_id')} を取り消しました。"
        return f"「{r.get('name')}」に送りました（言付け {r.get('message_id')}）。"
    return render
