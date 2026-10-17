"""ECOBuildのCLI：本体＋同梱の拡張（ecobuild_bundle）をコマンドで呼ぶ。コマンドの定義はcommandsパッケージに置き、CLIFrameWorkで組み立てる。

型ごとのコマンド（build・file・project 等）は型の拡張の cli パッケージにあり、今いるモジュールの型のものを重ねる（_types）。
"""

import json
import os
import sys
import types
from pathlib import Path

import click
from cli_framework import create_cli

from . import _catalog, _log, _types, commands
from ._output import USAGE_ERROR, use_utf8_when_redirected


# task --help の見出し（コマンドが多いので、目的ごとに分けて出す）
TASK_SECTIONS = (
    ("計画", ("new", "edit", "list", "next", "overdue", "workload", "comment", "close", "reopen")),
    ("作業", ("start", "commit", "add", "push", "status", "diff", "drop", "prune")),
    ("提出と完了", ("submit", "withdraw", "review", "approve", "reject", "finish", "revert")),
)


_CURRENT = object()


def build_cli(module_type: str | None | object = _CURRENT):
    """CLI を組み立てる。module_type：重ねる型のコマンド（既定：今いるディレクトリのモジュールの型。None＝重ねない）。"""
    if module_type is _CURRENT:
        module_type = _types.current(Path.cwd())
    cli = create_cli(commands, name="ecobuild", extensions=_types.extensions(module_type))
    if isinstance(cli, click.Group):
        _types.attach(cli, module_type)
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
    """入口。-C <パス>（--directory）は、コマンドの前に書いて別のディレクトリで実行する（git -C と同じ）。
    実行したことはログに残す（_log）。"""
    use_utf8_when_redirected()
    args = list(sys.argv[1:] if argv is None else argv)
    _log.start(args)
    code = None
    try:
        _main(args)
    except SystemExit as stop:
        code = stop.code if isinstance(stop.code, int) or stop.code is None else 1
        raise
    except BaseException:
        code = 1
        _log.logger.critical("予期しないエラー", exc_info=True, extra={"event": "command.crash"})
        raise
    finally:
        _log.finish(code)


def _main(args: list[str]) -> None:
    json_output = "--json" in args
    while args[:1] and args[0] in ("-C", "--directory"):
        if len(args) < 2:
            _usage_error("-C にはパスを指定してください。", json_output)
        try:
            os.chdir(args[1])
        except OSError as error:
            _usage_error(f"-C {args[1]}：{error.strerror}", json_output)
        args = args[2:]
    if json_output and "--help" in args:
        # コマンドの一覧・説明をJSONで（_catalog）。--help より前の、オプションでないものがコマンドの道筋
        path = []
        for arg in args:
            if arg.startswith("-"):
                break
            path.append(arg)
        sys.exit(_catalog.emit(build_cli, path, {("task",): TASK_SECTIONS}))
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
