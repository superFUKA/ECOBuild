"""ECOBuildのCLI：本体＋同梱の拡張（ecobuild_bundle）をコマンドで呼ぶ。コマンドの定義はcommandsパッケージに置き、CLIFrameWorkで組み立てる。

型ごとのコマンド（build・file・project 等）は型の拡張の cli パッケージにあり、今いるモジュールの型のものを重ねる（_types）。
"""

import os
import sys
import types
from pathlib import Path

import click
from cli_framework import create_cli
from ecobuild.errors import EcoBuildError

from . import _catalog, _effects, _errors, _extensions, _help, _inside, _log, _output, _types, commands
from ._output import use_utf8_when_redirected


# task --help の見出し（コマンドが多いので、目的ごとに分けて出す）
TASK_SECTIONS = (
    ("計画", ("new", "edit", "list", "next", "overdue", "workload", "comment", "close", "reopen")),
    ("作業", ("start", "commit", "add", "push", "status", "diff", "reset", "drop", "prune")),
    ("提出と完了", ("submit", "checks", "withdraw", "review", "approve", "reject", "finish", "revert")),
)


_CURRENT = object()


def build_cli(module_type: str | None | object = _CURRENT):
    """CLI を組み立てる。module_type：重ねる型のコマンド（既定：今いるディレクトリのモジュールの型。None＝重ねない）。"""
    _help.install()
    if module_type is _CURRENT:
        module_type = _types.current(Path.cwd())
    cli = create_cli(commands, name="ecobuild", extensions=_types.extensions(module_type))
    if isinstance(cli, click.Group):
        _types.attach(cli, module_type)
        _hide(cli)
    task = cli.commands.get("task") if isinstance(cli, click.Group) else None
    if isinstance(task, click.Group):
        task.format_commands = types.MethodType(_format_sections(TASK_SECTIONS), task)
    return cli


def _hide(cli: click.Group) -> None:
    """一覧に出さないコマンド（_effects.HIDDEN）を隠す。打てば動く。"""
    for path in _effects.HIDDEN:
        command = cli
        for name in path.split():
            command = command.commands.get(name) if isinstance(command, click.Group) else None
        if command is not None:
            command.hidden = True


def version() -> str | None:
    """入っている ECOBuild の版（ecobuild --version）。"""
    from importlib import metadata
    try:
        return metadata.version("ecobuild")
    except metadata.PackageNotFoundError:
        return None


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
            with formatter.section(f"コマンド（{title}）"):    # ほかのグループの「コマンド:」とそろえる
                formatter.write_dl(rows)

    return format_commands


def main(argv: list[str] | None = None) -> None:
    """入口。-C <パス>（--directory）は、コマンドの前に書いて別のディレクトリで実行する（git -C と同じ）。
    実行したことはログに残す（_log）。終了コードが0でなければ、どの出口でもログに command.error がある。"""
    use_utf8_when_redirected()
    _help.install()
    args = list(sys.argv[1:] if argv is None else argv)
    _log.start(args)
    _output.emitted = False
    code = None
    try:
        _main(args)
    except SystemExit as stop:
        code = stop.code if isinstance(stop.code, int) or stop.code is None else 1
        raise
    except KeyboardInterrupt:
        code = 130
        _log.logger.warning("中断しました", extra={"event": "command.interrupted"})
        raise
    except BaseException as error:
        code = 1
        if _output.output_closed(error):
            # 読む側が先に終わった（| head 等）：traceback を出さずに終える
            _log.logger.warning("出力の先が閉じました", extra={"event": "command.output_closed"})
            _quiet_output()
            raise SystemExit(code) from None
        _log.logger.critical("予期しないエラー", exc_info=True, extra={"event": "command.crash"})
        if not _output.json_requested:
            raise
        if not _output.emitted:      # --json なら、ほかの誤りと同じ形の JSON で
            _output.fail(_output.attempted, None, _errors.unexpected(error))
        raise SystemExit(code) from None
    finally:
        _log.finish(code)


def _quiet_output() -> None:
    """閉じた出力へ書かないように（終わるときの flush で、もう一度失敗しないよう）。"""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        for stream in (sys.stdout, sys.stderr):
            try:
                os.dup2(devnull, stream.fileno())
            except (OSError, ValueError):
                pass
    except OSError:
        pass


GLOBAL_FLAGS = ("--json",)    # コマンドの前にも書けるもの（後ろへ回す。ecobuild --json status ＝ ecobuild status --json）


def _main(args: list[str]) -> None:
    json_output = "--json" in args
    _output.json_requested = json_output
    _output.attempted = None
    while args[:1] and args[0] in ("-C", "--directory", *GLOBAL_FLAGS):
        if args[0] in GLOBAL_FLAGS:
            args = [*args[1:], args[0]]
            if all(arg.startswith("-") for arg in args):
                break        # ecobuild --json --help 等：コマンドがない
            continue
        if len(args) < 2:
            _usage_error("-C にはパスを指定してください。", json_output)
        try:
            os.chdir(args[1])
        except OSError as error:
            _usage_error(f"-C {args[1]}：{error.strerror}", json_output)
        args = args[2:]
    _output.attempted = _attempted(args)
    if args[:1] == ["--version"]:
        found = version()
        if json_output:
            _output.print_document({"ok": True, "command": "version", "module": None,
                                    "result": {"version": found}, "notices": [], "error": None})
        else:
            click.echo(f"ecobuild {found or '（版が分かりません）'}")
        sys.exit(0)
    inside = _inside.route(args, json_output)    # 作業空間がコンテナなら、ビルド等は中の ecobuild で
    if inside is not None:
        sys.exit(inside)
    external = _external(args[0]) if args and not args[0].startswith("-") else None
    if external:
        # 外部サブコマンド（ecobuild-<名前>。git と同じ）：引数ごと渡し、その終了コードで終わる
        sys.exit(_extensions.run(external, args[1:]))
    if json_output and "--help" in args:
        # コマンドの一覧・説明をJSONで（_catalog）。--help より前の、オプションでないものがコマンドの道筋
        path = []
        for arg in args:
            if arg.startswith("-"):
                break
            path.append(arg)
        sys.exit(_catalog.emit(build_cli, path, {("task",): TASK_SECTIONS}))
    try:
        code = build_cli().main(args, prog_name="ecobuild", standalone_mode=False)
    except click.UsageError as error:
        if json_output:
            _usage_error(_usage_message(error), json_output)
        # 人向け：使い方と日本語の説明は CLIFrameWork の表示のまま。ログには誤りとして残す
        _show_error(error)
        _output.log_error(_output.attempted, EcoBuildError(_errors.ErrorCode.USAGE_ERROR, _usage_message(error)))
        sys.exit(error.exit_code)
    except click.ClickException as error:
        _show_error(error)
        _output.log_error(_output.attempted, EcoBuildError(_errors.ErrorCode.FAILED, error.format_message()))
        sys.exit(error.exit_code)
    except click.exceptions.Abort:
        if not json_output:
            click.echo("中断しました。", err=True)
        sys.exit(1)
    except click.exceptions.Exit as exit_error:
        sys.exit(exit_error.exit_code)
    sys.exit(code if isinstance(code, int) else 0)


def _attempted(args: list[str]) -> str | None:
    """引数のうち、コマンドの名前の部分（"task start" 等。引数の誤りの JSON の command）。分からなければ None。"""
    words = []
    for arg in args:
        if arg.startswith("-"):
            break
        words.append(arg)
    known = _types.routes(commands).union(*_types.all_routes().values())
    for length in range(len(words), 0, -1):
        if tuple(words[:length]) in known:
            return " ".join(words[:length])
    return None


def _external(name: str) -> str | None:
    """name が ecobuild のコマンド（共通・どれかの型）でなく、PATH に ecobuild-<name> があれば、その場所。"""
    if (name,) in _types.routes(commands) or any((name,) in found for found in _types.all_routes().values()):
        return None
    return _extensions.find(name)


def _show_error(error: click.ClickException) -> None:
    """人向けの誤りの表示（CLIFrameWork と同じ日本語の文。使い方の行も）。"""
    try:
        from cli_framework.click_localization import _show_error as show
        show(error)
    except ImportError:  # 日本語化のない版
        error.show()


def _usage_message(error: click.UsageError) -> str:
    """引数の誤りの説明。人向けの表示と同じ日本語の文（CLIFrameWork）を使う。"""
    try:
        from cli_framework.click_localization import _usage_message as localized
        return localized(error)
    except ImportError:  # 日本語化のない版
        return error.format_message()


def _usage_error(message: str, json_output: bool) -> None:
    """引数の誤り。--json なら、エージェントが読めるようにJSONで返す（終了コードは2）。"""
    sys.exit(_output.usage_error(message, json_output))
