import sys
from typing import Annotated

import click

from ... import tooling
from ...errors import EcoBuildError, ErrorCode
from .._output import Invocation, execute, lines


class _Terminal(tooling.Questions):
    """端末で聞く。yes なら聞かずに既定の答えを使う。"""

    def __init__(self, yes: bool):
        self.yes = yes
        self.interactive = not yes

    def confirm(self, prompt: str, default: bool = True) -> bool:
        return default if self.yes else click.confirm(prompt, default=default, err=True)

    def ask(self, prompt: str, default: str = "") -> str:
        if self.yes:
            return default
        return click.prompt(prompt, default=default, show_default=bool(default), err=True)

    def info(self, message: str) -> None:
        click.echo(message, err=True)


def command(
    yes: Annotated[bool, "質問せず、既定の答え（今の値・導入する）で進める"] = False,
    json: Annotated[bool, "結果をJSONで出力する（--yes と一緒に使う）"] = False,
) -> int:
    """ECOBuildを使い始める準備を、質問しながら行います（インストーラーの最後に実行されます。何度実行してもよい）。

    設定を置くディレクトリ、足りないツールの導入、GitHubへのログイン（ボードの権限も）、gitの名前・メール、
    new・clone の既定の所有者。質問しない準備は ecobuild setup。
    """

    def action(inv):
        if not yes and (json or not sys.stdin.isatty()):
            raise EcoBuildError(ErrorCode.CONFIRMATION_REQUIRED, "ecobuild init は端末で質問しながら進めます。",
                                hint="端末で実行するか、--yes（既定の答えで進める）を付けてください。"
                                     "質問しない準備は ecobuild setup です。")
        inv.info("ECOBuild の準備を始めます（Enter で [ ] の中の答えを使います）。")
        return tooling.initialize(_Terminal(yes))

    def render(r):
        required = [i for i in r.remaining if i.required]
        return lines(
            "",
            "\n".join(f"行いました：{d}" for d in r.done) or "変えたものはありません",
            "\n".join(f"行いませんでした：{s}" for s in r.skipped) or None,
            "\n".join(f"まだ足りません：{i.name}（{i.hint}）" for i in required) or None,
            "\n".join(f"任意：{i.name}（{i.hint}）" for i in r.remaining if not i.required) or None,
            f"設定を置くディレクトリ：{r.home}",
            "準備ができました。ecobuild new <名前> で新しいモジュールを作るか、ecobuild clone <リポジトリ> で"
            "今あるモジュールを使えます（ecobuild --help で一覧）。" if not required else
            "足りないものを用意してから、もう一度 ecobuild init を実行してください（ecobuild doctor で確認できます）。",
        )

    return execute("init", Invocation(json_output=json, yes=yes), action, render)
