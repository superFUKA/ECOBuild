import sys
from typing import Annotated

import click
from ecobuild_agent import module_lead, operator

from ... import _effects
from ..._module import PROGRAM


def command(role: Annotated[str, "どのエージェントのフックか：operator（既定）か module（モジュールの進行役）"] = "operator") -> int:
    """オペレーター・進行役のフック（エージェントの設定から呼ばれます。人が使うものではありません）。

    標準入力のフックの入力（JSON）のシェルのコマンドを調べ、ecobuild と読むだけのコマンド以外・確認なしの重い操作を止めます
    （終了コード 2。理由は標準エラーに出し、エージェントに伝わります）。
    """
    if role == "module":    # モジュールの進行役：ecobuild（チームの操作も）と、読むだけの git・gh
        code, message = module_lead.guard(sys.stdin.read(), _effects.classify_module_lead, program=PROGRAM)
        if message:
            click.echo(message, err=True)
        return code
    extra = operator.effects()     # 拡張が名乗った重さ（一式を置いたときに読んだもの）
    code, message = operator.guard(sys.stdin.read(), lambda args: _effects.classify(args, extra), program=PROGRAM)
    if message:
        click.echo(message, err=True)
    return code
