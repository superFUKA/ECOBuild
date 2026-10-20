"""作業空間をコンテナにしていれば、ビルド・テスト等のコマンドをコンテナの中の ecobuild に渡す（出力・終了コードはそのまま）。

渡すのは、型のツール（コンパイラー等）を動かすコマンドだけ（COMMANDS）。git・GitHub の操作はこのPCで行う（ファイルは同じ）。
中の ecobuild は環境変数（container.INSIDE）で中にいると分かるので、もう一度は渡さない。
--json の結果の中の場所（/work…）は、このPCの場所に読み替えて出す。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import click
from ecobuild import workspaces
from ecobuild.errors import WorkError
import ecobuild_container as container

from ._module import PROGRAM
from ._output import Invocation, execute

COMMANDS = ("build", "test", "run", "clean", "rebuild", "check")


def route(args: list[str], json_output: bool) -> int | None:
    """コンテナの中で実行したら、その終了コード。このPCで実行するものなら None。"""
    words = [a for a in args if not a.startswith("-")]
    if os.environ.get(container.INSIDE) or not words or words[0] not in COMMANDS or "--help" in args:
        return None
    try:
        root = workspaces.module_root(Path.cwd())
        if not container.enabled(root):
            return None
    except WorkError:
        return None
    from .commands.container._source import source
    try:
        code, out = container.run_inside(root, [PROGRAM, *args], cwd=Path.cwd(), command=PROGRAM, source=source(),
                                         progress=lambda message: click.echo(message, err=True), capture=json_output)
    except WorkError as error:
        def fail(inv):
            raise error
        return execute(words[0], Invocation(json_output=json_output), fail)
    for line in out.splitlines():
        try:
            line = json.dumps(container.outside(json.loads(line), root), ensure_ascii=False)
        except ValueError:
            pass
        click.echo(line)
    return code
