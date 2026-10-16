"""ECOBuildのCLI：本体＋同梱の拡張（ecobuild_bundle）をコマンドで呼ぶ。コマンドの定義はcommandsパッケージに置き、CLIFrameWorkで組み立てる。"""

import json
import os
import sys
import types

import click
from cli_framework import create_cli

from . import commands
from ._output import USAGE_ERROR, use_utf8_when_redirected


# task --help の見出し（コマンドが多いので、目的ごとに分けて出す）
TASK_SECTIONS = (
    ("計画", ("new", "edit", "list", "next", "overdue", "workload", "comment", "close", "reopen")),
    ("作業", ("start", "commit", "add", "push", "status", "diff", "drop", "prune")),
    ("提出と完了", ("submit", "withdraw", "review", "approve", "reject", "finish", "revert")),
)


def build_cli():
    cli = create_cli(commands, name="ecobuild")
    task = cli.commands.get("task") if isinstance(cli, click.Group) else None
    if isinstance(task, click.Group):
        task.format_commands = types.MethodType(_format_sections(TASK_SECTIONS), task)
    return cli


def _format_sections(sections):
    """グループのコマンドの一覧を、見出しごとに出す（見出しにないコマンドは「その他」）。"""

    def format_commands(self, ctx, formatter):
        names = self.list_commands(ctx)
        listed = set()
        groups = []
        for title, members in (*sections, ("その他", tuple(names))):
            rows = []
            for name in members:
                command = self.get_command(ctx, name)
                if name in listed or name not in names or command is None or command.hidden:
                    continue
                listed.add(name)
                rows.append((name, command.get_short_help_str(limit=formatter.width)))
            if rows:
                groups.append((title, rows))
        for title, rows in groups:
            with formatter.section(title):
                formatter.write_dl(rows)

    return format_commands


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
    if not json_output:
        # 人向け：エラーの表示（日本語）と終了コードは CLIFrameWork に任せる。
        build_cli().main(args, prog_name="ecobuild")
        return
    try:
        code = build_cli().main(args, prog_name="ecobuild", standalone_mode=False)
    except click.UsageError as error:
        _usage_error(_usage_message(error), json_output)
    except click.exceptions.Abort:
        sys.exit(1)
    except click.exceptions.Exit as exit_error:
        sys.exit(exit_error.exit_code)
    sys.exit(code if isinstance(code, int) else 0)


def _usage_message(error: click.UsageError) -> str:
    """引数の誤りの説明。人向けの表示と同じ日本語の文（CLIFrameWork）を使う。"""
    try:
        from cli_framework.click_localization import _usage_message as localized
        return localized(error)
    except ImportError:  # 日本語化のない版
        return error.format_message()


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
