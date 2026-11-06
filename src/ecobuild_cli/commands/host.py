from typing import Annotated

from .._inside import COMMANDS
from .._output import usage_error


def command(*args: Annotated[str, f"このPCで実行するコマンドと、その引数（{'・'.join(COMMANDS)}）"]) -> int:
    """コンテナにした作業空間でも、ビルド・テスト等をこのPC（Windows 等）で実行します。

    例：ecobuild host build、ecobuild host test --filter foo。コンテナにしていない作業空間では、host を付けないのと同じです。
    コンテナの中のエージェントに、このPCでの実行を許すのは ecobuild container set --host-run on（作業空間ごと。既定は許さない）。
    """
    # 実行できるもの（ecobuild host build 等）は、入口（ecobuild_cli._main）が host を外してこのPCで実行する。ここへ来るのは
    # コマンドがない・知らないコマンドのときだけ
    if not args:
        return usage_error(f"このPCで実行するコマンドを指定してください（{'・'.join(COMMANDS)}）。", False)
    return usage_error(f"このPCで実行できるのは {'・'.join(COMMANDS)} だけです：{args[0]}", False)
