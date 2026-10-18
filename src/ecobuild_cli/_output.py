"""CLIの共通処理：人向けの表示とJSON、終了コード、確認の扱い。

--json を指定したときは、標準出力にJSONを1つだけ出す。それ以外の表示は標準エラーへ出す。
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click

from ecowork import WorkError

from ecobuild import workspaces as _workspaces
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_cli._module import Module

from . import _log

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
            self.use_module(Module.find(self.cwd))
        return self._module

    def use_module(self, module: Module) -> None:
        """対象のモジュール。このPCの作業空間の記録（workspace list）にも入れる（以前からあるcloneも、使えば記録される）。"""
        self._module = module
        _log.use_module(module.root)
        _workspaces.record_quietly(module.root)

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
        _log.logger.info("%s", message, extra={"event": "progress"})
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
        error = _repository_state(error)
        _log.logger.error("%s", error.message, exc_info=True, extra={"event": "command.error", "data": {
            "command": command, "code": error.code, "message": error.message, "hint": error.hint,
            "details": to_data(error.details)}})
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
    _log.logger.debug("%s", command, extra={"event": "command.result", "data": {
        "command": command, "result": to_data(result), "notices": _notices(invocation)}})
    if invocation.json_output:
        _emit_json(command, invocation, result, None)
    else:
        if render is not None:
            text = render(result)
            if text:
                click.echo(text)
        for notice in _notices(invocation):
            click.echo(f"お知らせ：{notice}", err=True)
    return SUCCESS


# GitHub（gh・git）の失敗の出力から、リポジトリがECOBuildの外で変わったことを見分ける
_ARCHIVED = re.compile(r"archived so (?:it )?is read-only|repository was archived", re.IGNORECASE)
_GONE = re.compile(r"repository not found|repository '[^']*' not found|could not resolve to a repository",
                   re.IGNORECASE)


def _repository_state(error: WorkError) -> WorkError:
    """git・gh の一般的な失敗のうち、GitHubでリポジトリがアーカイブ・削除されたためのものを、そう分かる形にする。"""
    if error.code not in (ErrorCode.GIT_ERROR, ErrorCode.GITHUB_ERROR):
        return error
    text = f"{error.message} {error.details or ''}"
    if _ARCHIVED.search(text):
        return EcoBuildError(ErrorCode.REPOSITORY_ARCHIVED,
                             "GitHubのリポジトリがアーカイブ（読み取り専用）されているため、変更できません。",
                             hint="元に戻すには ecobuild module unarchive <所有者/名前>（名前は ecobuild module show で"
                                  "確かめられます）。", details=error.details)
    if _GONE.search(text):
        return EcoBuildError(ErrorCode.REPOSITORY_NOT_FOUND,
                             "GitHubのリポジトリが見つかりません（削除されたか、見る権限がなくなった可能性があります）。",
                             hint="ecobuild module list で確かめてください。削除したリポジトリは、90日以内なら"
                                  "GitHubのアカウントの設定から戻せます。", details=error.details)
    return error


def _notices(invocation: Invocation) -> list[str]:
    """操作は成功したが知らせておくこと（親タスクの子がすべて閉じた等）。"""
    module = invocation._module
    return [] if module is None else list(module.repository.notices)


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

_BUILD_WORDS = {"build": ("ビルド中", "ビルドしました"), "clean": ("クリーン中", "クリーンしました"),
                "rebuild": ("リビルド中", "リビルドしました")}


def build_like(command: str, project: str, configuration: str, profile: str, json_output: bool) -> int:
    """build・clean・rebuild の共通の入口。"""
    doing, done = _BUILD_WORDS[command]

    def action(inv):
        module = inv.module
        target = project or module.project_at(inv.cwd)
        options, name = module.build_options(configuration, profile or None)
        inv.info(f"{doing}：{target or '全体'}（{options.configuration}" + (f"、{name}" if name else "") + "）")
        return module.build(project=target, configuration=configuration, profile=profile or None, action=command)

    return run_command(command, action, lambda r: f"{done}：{r.project or '全体'}（{r.configuration}）",
                       json_output=json_output)


def missing(option: str, json_output: bool = False) -> int:
    """必須のオプションがない（CLIFrameWorkでは既定値付き＝省略可能になるため、ここで確かめる）。"""
    return usage_error(f"{option} を指定してください。", json_output)


def usage_error(message: str, json_output: bool) -> int:
    """引数の誤り。--json ならJSONで返す。終了コードは2。"""
    if json_output:
        click.echo(json.dumps({"ok": False, "command": None, "module": None, "result": None,
                               "error": {"code": "usage_error", "message": message,
                                         "hint": "ecobuild <コマンド> --help で使い方を確認してください。",
                                         "details": None}}, ensure_ascii=False))
    else:
        click.echo(f"エラー：{message}", err=True)
    return USAGE_ERROR


def optional_argument(values: tuple, option_value: Any, option: str, json_output: bool) -> Any:
    """省略可能な引数は、位置引数でもオプションでも受ける（task status 12 と task status --issue 12）。

    CLIFrameWorkでは省略可能な位置引数を作れないため、可変長の位置引数で受けて0個か1個に限る。
    誤りは用法エラー（終了コード2）にする。
    """
    if len(values) > 1:
        message = f"引数は1つだけ指定してください：{' '.join(map(str, values))}"
    elif values and option_value:
        message = f"引数 {values[0]} と {option} の両方は指定できません。どちらか1つにしてください。"
    else:
        return values[0] if values else option_value
    raise click.exceptions.Exit(usage_error(message, json_output))


def split_list(text: str) -> tuple[str, ...]:
    """カンマ区切りの値（--label bug,docs 等）。空なら空。"""
    return tuple(part.strip() for part in text.split(",") if part.strip())


def split_semicolons(text: str) -> tuple[str, ...]:
    """セミコロン区切りの値（コンパイルオプション等。値にカンマを含められる。CMakeの引数のリストの区切りでもある）。"""
    return tuple(part.strip() for part in text.split(";") if part.strip())


def split_numbers(text: str, option: str, json_output: bool) -> tuple[int, ...]:
    """カンマ区切りのIssueの番号（--blocked-by 3,5 等。# は付けても付けなくてもよい）。誤りは用法エラー。"""
    numbers = []
    for part in split_list(text):
        value = part.removeprefix("#")
        if not value.isdigit():
            raise click.exceptions.Exit(usage_error(f"{option} にはIssueの番号を指定してください：{part}", json_output))
        numbers.append(int(value))
    return tuple(numbers)


def local_time(timestamp: str, format: str = "%Y-%m-%d") -> str:
    """GitHub・gitの時刻（ISO 8601。UTC や書いた人の時差のもの）を、このPCの時刻で表示する。読めなければそのまま切る。"""
    try:
        return datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone().strftime(format)
    except ValueError:
        return timestamp[:len(datetime.datetime(2000, 1, 1).strftime(format))]


def lines(*parts: str | None) -> str:
    return "\n".join(part for part in parts if part)


def upgrade_note(r) -> str | None:
    """モジュールの仕様の版が古ければ、その案内（status・module show。r に format・latest_format）。"""
    if r.format >= r.latest_format:
        return None
    return (f"このモジュールは以前の ECOBuild の仕様（版 {r.format}）です。ecobuild module upgrade で今の版 "
            f"{r.latest_format} に合わせられます（タスクブランチで。--dry-run で変わるファイルを確認）")


DETAIL_LINES = 30


def _detail_text(details: Any) -> str:
    """人向けに、詳細（外部ツールの出力等）の末尾だけを表示する。全文は --json の error.details にある。"""
    if not details:
        return ""
    if isinstance(details, (list, tuple)):
        return "\n".join(f"  {_item_text(item)}" for item in details)
    if isinstance(details, dict):
        details = details.get("output") or json.dumps(to_data(details), ensure_ascii=False)
    text_lines = str(details).rstrip().splitlines()
    shown = text_lines[-DETAIL_LINES:]
    omitted = len(text_lines) - len(shown)
    if not omitted:
        return "\n".join(f"  {line}" for line in shown)
    # 並列ビルド等でエラーの行が末尾より前にあっても見えるよう、省略した部分のエラーの行は残す。
    errors = [line for line in text_lines[:omitted] if _ERROR_LINE.search(line)][:DETAIL_LINES]
    head = f"  …（前の{omitted}行は省略" + ("。そのうちエラーの行" if errors else "") + "。全文は --json で確認できます）"
    return "\n".join([head] + [f"  {line}" for line in errors] + (["  …"] if errors else [])
                     + [f"  {line}" for line in shown])


_ERROR_LINE = re.compile(r"\b(error|fatal error)\b|FAILED", re.IGNORECASE)


def _item_text(item: Any) -> str:
    """詳細の1項目を人向けに。CIの実行は「#番号 ワークフロー：結果 URL」、他の辞書は値を並べる（Pythonの辞書のまま出さない）。"""
    if not isinstance(item, dict):
        return str(item)
    if "name" in item and "ok" in item:      # check の項目
        from ecobuild.module import CHECK_NAMES
        return f"{'OK' if item['ok'] else 'NG'} {CHECK_NAMES.get(item['name'], item['name'])}" + (
            f"：{item['detail']}" if item.get("detail") else "")
    if "workflow" in item:
        return " ".join(str(p) for p in (f"#{item.get('id')}", f"{item.get('workflow')}："
                                          f"{item.get('conclusion') or item.get('status') or ''}", item.get("url"))
                        if p)
    return "・".join(f"{key} {value}" for key, value in item.items() if value not in (None, ""))


def to_data(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_data(getattr(value, field.name))
                for field in dataclasses.fields(value) if not field.name.startswith("_")}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, datetime.date):
        return value.isoformat()
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
        "notices": _notices(invocation),
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
