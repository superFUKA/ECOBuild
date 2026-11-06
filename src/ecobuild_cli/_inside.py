"""作業空間をコンテナにしていれば、ビルド・テスト等のコマンドをコンテナの中の ecobuild に渡す（出力・終了コードはそのまま）。

渡すのは、型のツール（コンパイラー等）を動かすコマンドだけ（COMMANDS）。git・GitHub の操作はこのPCで行う（ファイルは同じ）。
ecobuild host <コマンド> なら渡さず、このPCで実行する（入口が環境変数 container.HOST を立てる）。
中の ecobuild は環境変数（container.INSIDE）で中にいると分かるので、もう一度は渡さない。
渡している間は、このPCでその作業空間を使用中にする（usage.running。中の ecobuild は書かない：中の pid はこのPCでは
確かめられない）。
中の ecobuild の標準エラー（--json ならイベント：_events）は、そのまま通す。
--json の結果の中の場所（/work…）は、このPCの場所に読み替えて出す。
中の ecobuild のログには、このPCの run を forwarded_from に書いてもらう（_log.forward_environment）。中で失敗したら、
このPCのログにもその誤り（command.error。--json なら中の error）を書く。
"""

from __future__ import annotations

import json
from pathlib import Path

import click
from ecobuild import usage, workspaces
from ecobuild.errors import WorkError
import ecobuild_container as container

from . import _events, _log
from ._module import PROGRAM
from ._output import Invocation, execute, log_error

COMMANDS = ("build", "test", "run", "clean", "rebuild", "check")


def route(args: list[str], json_output: bool) -> int | None:
    """コンテナの中で実行したら、その終了コード。このPCで実行するものなら None。"""
    words = [a for a in args if not a.startswith("-")]
    if not words or words[0] not in COMMANDS or "--help" in args:
        return None
    try:
        root = workspaces.module_root(Path.cwd())
        if not container.routed(root):   # コンテナにしていない・中にいる・このPCで実行する（ecobuild host）
            return None
    except WorkError:
        return None
    from .commands.container._source import source
    passed = [f"{key}={value}" for key, value in _log.forward_environment().items()]
    command = ["env", *passed, PROGRAM, *args] if passed else [PROGRAM, *args]
    try:
        with usage.running(root, words[0]):
            code, out = container.run_inside(root, command, cwd=Path.cwd(), command=PROGRAM, source=source(),
                                             progress=lambda message: _events.progress(message, json_output),
                                             capture=json_output)
    except WorkError as error:
        def fail(inv):
            raise error
        return execute(words[0], Invocation(json_output=json_output), fail)
    error = None
    for line in out.splitlines():
        try:
            document = container.outside(json.loads(line), root)
            line = json.dumps(document, ensure_ascii=False)
            if isinstance(document, dict) and isinstance(document.get("error"), dict):
                error = document["error"]
        except ValueError:
            pass
        click.echo(line)
    _log.logger.info("コンテナの中の ecobuild：終了コード %s", code, extra={"event": "command.forwarded", "data": {
        "command": " ".join(words[:2]), "exit_code": code, "container": container.name(root)}})
    if code:
        log_error(" ".join(words[:2]), WorkError(
            str((error or {}).get("code") or "failed"),
            str((error or {}).get("message") or f"コンテナの中の ecobuild が終了コード {code} で終わりました。"),
            hint=(error or {}).get("hint") or "詳しくはコンテナの中のログ（モジュールの .ecobuild/logs/ の、forwarded_from が"
                                              "この run のもの）を見てください。",
            details=(error or {}).get("details")))
    return code
