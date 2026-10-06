"""ECOBuildのCLI。コマンドの定義はcommandsパッケージに置き、CLIFrameWorkで組み立てる。"""

import json
import os
import sys

import click
from cli_framework import create_cli

from . import commands
from ._output import USAGE_ERROR, use_utf8_when_redirected


def build_cli():
    return create_cli(commands, name="ecobuild")


def main(argv: list[str] | None = None) -> None:
    """入口。-C <パス>（--directory）は、コマンドの前に書いて別のディレクトリで実行する（git -C と同じ）。"""
    use_utf8_when_redirected()
    args = list(sys.argv[1:] if argv is None else argv)
    json_output = "--json" in args
    while args[:1] and args[0] in ("-C", "--directory"):
        if len(args) < 2:
            _usage_error("-C にはパスを指定してください。", json_output)
        try:
            os.chdir(args[1])
        except OSError as error:
            _usage_error(f"-C {args[1]}：{error.strerror}", json_output)
        args = args[2:]
    try:
        code = build_cli().main(args, prog_name="ecobuild", standalone_mode=False)
    except click.UsageError as error:
        if not json_output:
            error.show()
            sys.exit(USAGE_ERROR)
        _usage_error(error.format_message(), json_output)
    except click.exceptions.Abort:
        click.echo("中止しました。", err=True)
        sys.exit(1)
    except click.exceptions.Exit as exit_error:
        sys.exit(exit_error.exit_code)
    sys.exit(code if isinstance(code, int) else 0)


def _usage_error(message: str, json_output: bool) -> None:
    """引数の誤り。--json なら、エージェントが読めるようにJSONで返す（終了コードは2）。"""
    if json_output:
        document = {"ok": False, "command": None, "module": None, "result": None,
                    "error": {"code": "usage_error", "message": message,
                              "hint": "ecobuild <コマンド> --help で使い方を確認してください。", "details": None}}
        click.echo(json.dumps(document, ensure_ascii=False))
    else:
        click.echo(f"エラー：{message}", err=True)
    sys.exit(USAGE_ERROR)
