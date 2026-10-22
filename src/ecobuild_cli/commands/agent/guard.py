import sys

import click
from ecobuild_agent import guard

from ... import _effects
from ..._module import PROGRAM


def command() -> int:
    """シェルのコマンドの関所（エージェントの設定から呼ばれます。人が使うものではありません）。

    標準入力のフックの入力（JSON）のシェルのコマンドを調べ、ecobuild と読むだけのコマンド以外・確認なしの重い操作を止めます
    （終了コード 2。理由は標準エラーに出し、エージェントに伝わります）。
    """
    code, message = guard.hook(sys.stdin.read(), _effects.classify, program=PROGRAM)
    if message:
        click.echo(message, err=True)
    return code
