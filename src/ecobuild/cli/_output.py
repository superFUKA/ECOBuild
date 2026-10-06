"""CLIの共通処理：人向けの表示とJSON、終了コード、確認の扱い。

--json を指定したときは、標準出力にJSONを1つだけ出す。それ以外の表示は標準エラーへ出す。
"""

from __future__ import annotations

import dataclasses
import enum
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click

from ecowork import WorkError

from ..errors import EcoBuildError, ErrorCode
from ..module import Module

SUCCESS = 0
FAILURE = 1


class Invocation:
    """1回のコマンド実行。対象のモジュールを必要になったときに探して覚える。"""

    def __init__(self, *, json_output: bool, yes: bool = False, cwd: Path | None = None):
        self.json_output = json_output
        self.yes = yes
        self.cwd = Path.cwd() if cwd is None else cwd
        self._module: Module | None = None

    @property
    def module(self) -> Module:
        if self._module is None:
            self._module = Module.find(self.cwd)
        return self._module

    def use_module(self, module: Module) -> None:
        self._module = module

    def confirm(self, prompt: str) -> None:
        """確認が必要な操作。端末でない場合や--json時は質問せず、--yesがなければ失敗する。"""
        if self.yes:
            return
        if self.json_output or not sys.stdin.isatty():
            raise EcoBuildError(
                ErrorCode.CONFIRMATION_REQUIRED,
                f"確認が必要です：{prompt}",
                hint="内容を確認し、--yes を付けて実行してください。",
            )
        if not click.confirm(prompt, default=False, err=True):
            raise click.Abort()

    def info(self, message: str) -> None:
        """人向けの進捗。--json時も標準エラーなのでJSONを壊さない。"""
        click.echo(message, err=True)


def execute(
    command: str,
    invocation: Invocation,
    action: Callable[[Invocation], Any],
    render: Callable[[Any], str | None] | None = None,
) -> int:
    try:
        result = action(invocation)
    except WorkError as error:
        if invocation.json_output:
            _emit_json(command, invocation, None, error)
        else:
            click.echo(f"エラー：{error.message}", err=True)
            detail = _detail_text(error.details)
            if detail:
                click.echo(detail, err=True)
            if error.hint:
                click.echo(f"ヒント：{error.hint}", err=True)
        return FAILURE
    if invocation.json_output:
        _emit_json(command, invocation, result, None)
    elif render is not None:
        text = render(result)
        if text:
            click.echo(text)
    return SUCCESS


def run_command(
    command: str,
    action: Callable[[Invocation], Any],
    render: Callable[[Any], str | None] | None = None,
    *,
    json_output: bool,
    yes: bool = False,
) -> int:
    """各コマンドの入口。対象のモジュールは今いるディレクトリから探す。"""
    return execute(command, Invocation(json_output=json_output, yes=yes), action, render)


USAGE_ERROR = 2


def missing(option: str) -> int:
    """必須のオプションがない（CLIFrameWorkでは既定値付き＝省略可能になるため、ここで確かめる）。"""
    click.echo(f"エラー：{option} を指定してください。", err=True)
    return USAGE_ERROR


def lines(*parts: str | None) -> str:
    return "\n".join(part for part in parts if part)


DETAIL_LINES = 30


def _detail_text(details: Any) -> str:
    """人向けに、詳細（外部ツールの出力等）の末尾だけを表示する。全文は --json の error.details にある。"""
    if not details:
        return ""
    if isinstance(details, (list, tuple)):
        return "\n".join(f"  {item}" for item in details)
    if isinstance(details, dict):
        details = details.get("output") or json.dumps(to_data(details), ensure_ascii=False)
    text_lines = str(details).rstrip().splitlines()
    shown = text_lines[-DETAIL_LINES:]
    omitted = len(text_lines) - len(shown)
    return "\n".join(([f"  …（前の{omitted}行は省略。全文は --json で確認できます）"] if omitted else [])
                     + [f"  {line}" for line in shown])


def to_data(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_data(getattr(value, field.name))
                for field in dataclasses.fields(value) if not field.name.startswith("_")}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(key): to_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_data(item) for item in value]
    return value


def _emit_json(command: str, invocation: Invocation, result: Any, error: WorkError | None) -> None:
    module = invocation._module
    document = {
        "ok": error is None,
        "command": command,
        "module": None if module is None else module.root.as_posix(),
        "result": None if error is not None else to_data(result),
        "error": None if error is None else {
            "code": error.code,
            "message": error.message,
            "hint": error.hint,
            "details": to_data(error.details),
        },
    }
    click.echo(json.dumps(document, ensure_ascii=False))


def use_utf8_when_redirected() -> None:
    """パイプやファイルへ出すとき（エージェントが読むとき）は、OSの文字コードによらずUTF-8で出す。"""
    for stream in (sys.stdout, sys.stderr):
        if not stream.isatty() and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
