import sys

import click
from ecobuild_agent import guard


def command() -> int:
    """作業空間のエージェントのシェルの関所（エージェントの設定から呼ばれます。人が使うものではありません）。

    標準入力のフックの入力（JSON）のシェルのコマンドを調べ、ecobuild・gh と、git で書き込む操作（commit・push・
    switch・worktree 等）を止めます（終了コード 2。理由は標準エラーに出し、エージェントに伝わります）。ほかは通します。
    """
    code, message = guard.hook(sys.stdin.read())
    if message:
        click.echo(message, err=True)
    return code
