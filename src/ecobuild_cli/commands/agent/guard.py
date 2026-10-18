import sys

import click
from ecobuild_bundle import operator

from ... import _effects
from ..._module import PROGRAM


def command() -> int:
    """オペレーターのフック（エージェントの設定から呼ばれます。人が使うものではありません）。

    標準入力のフックの入力（JSON）のシェルのコマンドを調べ、ecobuild と読むだけのコマンド以外・確認なしの重い操作を止めます
    （終了コード 2。理由は標準エラーに出し、エージェントに伝わります）。
    """
    extra = operator.effects()     # 拡張が名乗った重さ（一式を置いたときに読んだもの）
    code, message = operator.guard(sys.stdin.read(), lambda args: _effects.classify(args, extra), program=PROGRAM)
    if message:
        click.echo(message, err=True)
    return code
