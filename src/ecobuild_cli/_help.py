"""CLIFrameWork の表示のうち、ECOBuild で変えるもの（install で1回だけ差し替える）。

- オプションの既定値（ecobuild <コマンド> --help）：既定がない（空の文字列）・付けないのが既定の真偽のオプションには
  書かない（[既定値: ] や [既定値: no-draft] は読みにくく、説明の「既定は〇〇」と食い違って見える）。
  付けるのが既定の真偽のオプションだけ、外す書き方と一緒に書く（[既定値: --check。外すには --no-check]）。
- 付けないのが既定の真偽のオプションは、否定形（--no-…）を一覧に出さない（--no-deny / --no-no-deny 等が読みにくい）。
  否定形は今までどおり使え、--help --json の negative にある。
- 1つだけ受ける位置引数（可変長で受けて _output.optional_argument で 0〜1 個に限るもの）は、使い方の行に ... を付けない
  （[NUMBER]... と書くと、いくつも受けるように読める）。--help --json の multiple も false。
- コマンドの中の予期しない誤り（WorkError でない例外）：--json なら、ほかの誤りと同じ形の JSON で返し、ログに残す。
"""

from __future__ import annotations

import re

import click
from cli_framework import click_command, click_group
from cli_framework.click_localization import JapaneseOption
from ecobuild.errors import WorkError

_installed = False


def install() -> None:
    global _installed
    if _installed:
        return
    _installed = True
    global _original_metavar
    _original_metavar = click_command._DocumentedArgument.make_metavar
    click_command._DocumentedArgument.make_metavar = _argument_metavar
    JapaneseOption.get_help_record = _help_record
    click_command._report_application_error = _application_error
    click_group._report_application_error = _application_error


_SAME_AS_OPTION = re.compile(r"（--[\w-]+ と同じ")


def single_argument(argument: click.Argument) -> bool:
    """可変長の位置引数のうち、1つだけ受けるもの（_output.optional_argument で 0〜1 個に限る。説明に「（--〇〇 と同じ」）。"""
    return argument.nargs == -1 and bool(_SAME_AS_OPTION.search(getattr(argument, "help_text", None) or ""))


def _argument_metavar(self: click.Argument, *args, **kwargs) -> str:
    """位置引数の書き方（使い方の行）。1つだけ受けるものは [NUMBER]...ではなく [NUMBER]。"""
    metavar = _original_metavar(self, *args, **kwargs)
    return metavar.removesuffix("...") if single_argument(self) else metavar


def _help_record(self: click.Option, ctx: click.Context) -> tuple[str, str] | None:
    record = click.Option.get_help_record(self, ctx)
    if record is None:
        return None
    names, description = record
    note = default_note(self, ctx)
    if self.is_bool_flag and self.secondary_opts and not self.get_default(ctx, call=False):
        names = names.split(" / ")[0]
    return names, f"{description}  [{note}]".strip() if note else description


def default_note(option: click.Option, ctx: click.Context) -> str | None:
    """--help に書く既定値（書かないなら None）。"""
    default = option.get_default(ctx, call=False)
    if option.is_bool_flag:
        if not default:
            return None
        negative = f"。外すには {option.secondary_opts[0]}" if option.secondary_opts else ""
        return f"既定値: {option.opts[0]}{negative}"
    if default in (None, "", (), []) or callable(default):
        return None
    return f"既定値: {default}"


def _application_error(error: Exception, *, debug: bool) -> None:
    """CLIFrameWork がコマンドの例外を受けたとき（execute の外で起きたもの）。"""
    from . import _errors, _output
    if _output.output_closed(error):
        raise error
    if isinstance(error, click.exceptions.Abort):   # 確認で「いいえ」・Ctrl+C：不具合ではない（入口の main と同じ）
        if not _output.json_requested:
            click.echo("中断しました。", err=True)
        raise click.exceptions.Exit(1) from error
    if debug:
        import traceback
        traceback.print_exception(type(error), error, error.__traceback__)
    found = error if isinstance(error, WorkError) else _errors.unexpected(error)
    raise click.exceptions.Exit(_output.fail(_output.attempted, None, found)) from error
