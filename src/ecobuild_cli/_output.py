"""CLIの共通処理：人向けの表示とJSON、終了コード、確認の扱い。

--json を指定したときは、標準出力にJSONを1つだけ出す。それ以外の表示は標準エラーへ出す（_events。--json では1行1件の
JSON のイベント）。結果の JSON：{ok, command, module, result, notices, error, log}。log はこのコマンドのログ
（{run, file}。ログを書いていなければ null）。
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
import errno
import json
import os
import re
import sys
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import click

from ecowork import WorkError

from ecobuild import locks as _locks
from ecobuild_container import INSIDE as _IN_CONTAINER
from ecobuild import workspaces as _workspaces
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_cli._module import Module

from . import _errors, _events, _log

SUCCESS = 0
FAILURE = 1

# 今のコマンド（入口が引数から決める）：引数の誤り・予期しない誤りの JSON の command と、--json の有無
attempted: str | None = None
json_requested = False


class Invocation:
    """1回のコマンド実行。対象のモジュールを必要になったときに探して覚える。"""

    def __init__(self, *, json_output: bool, yes: bool = False, cwd: Path | None = None):
        self.json_output = json_output
        self.yes = yes
        self.cwd = Path.cwd() if cwd is None else cwd
        self._module: Module | None = None
        self.command = ""                 # 実行中のコマンドの名前（execute が決める）
        self.holds = ExitStack()          # コマンドの間だけ持つもの（作業空間のロック）
        self.notices: list[str] = []      # モジュールのない操作（workspace list 等）の知らせ

    @property
    def module(self) -> Module:
        if self._module is None:
            self.use_module(Module.find(self.cwd))
        return self._module

    def use_module(self, module: Module) -> None:
        """対象のモジュール。このPCのモジュールの一覧（workspace list）にも元の clone を入れる（以前からあるcloneも、
        使えば入る）。前のモジュールの知らせ（作業空間を作った元の clone 等）は引き継ぐ。"""
        if self._module is not None and self._module is not module:
            module.repository.notices[:0] = [n for n in self._module.repository.notices
                                             if n not in module.repository.notices]
        self._module = module
        _log.use_module(module.root)
        _workspaces.record_quietly(module.root)
        self._hold_workspace()

    def _hold_workspace(self) -> None:
        """ビルド・テスト等の実行中は、その作業空間をロックする（その間に作業空間が消えたり切り替わったりしないように。
        locks.COMMANDS）。コンテナの中では書かない：渡したこのPCの CLI がロックしている（_inside）。中の pid はこのPCでは
        確かめられず、書き直すとこのPCの記録を「終わった」とみなして消してしまう。"""
        if os.environ.get(_IN_CONTAINER):
            return
        if self._module is not None and self.command in _locks.COMMANDS:
            self.holds.enter_context(_locks.running(self._module.root, self.command))

    def confirm(self, prompt: str) -> None:
        """確認が必要な操作。端末でない場合や--json時は質問せず、--yesがなければ失敗する。"""
        if self.yes:
            return
        if self.json_output or not sys.stdin.isatty():
            raise confirmation_required(prompt)
        if not ask_confirm(prompt, default=False):
            raise click.Abort()

    def info(self, message: str) -> None:
        """経過（今していること。頭が「注意：」なら注意）。標準エラーへ（--json ではイベント）。ログにも書く。"""
        _log.logger.info("%s", message, extra={"event": "warning" if message.startswith("注意：") else "progress"})
        _events.progress(message, self.json_output)


def confirmation_required(prompt: str, option: str = "--yes") -> EcoBuildError:
    """確認が必要なのに、聞けない（--json・端末でない）か答えがない（入力が閉じている）ときの誤り。"""
    return EcoBuildError(ErrorCode.CONFIRMATION_REQUIRED, f"確認が必要です：{prompt}",
                         hint=f"内容を確認し、{option} を付けて実行してください（確認せずに実行します）。")


def _no_input(abort: click.exceptions.Abort) -> bool:
    """click の質問が、入力の終わり（標準入力が閉じている等）で Abort になった。Ctrl+C（中断）とは分ける。"""
    return isinstance(abort.__context__, EOFError)


def ask_confirm(prompt: str, *, default: bool, option: str = "--yes") -> bool:
    """端末で [y/N] を聞く（click.confirm）。答えがない（入力が閉じている）なら、option で確認せずに実行できると
    案内する誤り（予期しない Abort にしない）。Ctrl+C は今までどおり中断（click.Abort）。"""
    try:
        return click.confirm(prompt, default=default, err=True)
    except click.exceptions.Abort as abort:
        if _no_input(abort):
            raise confirmation_required(prompt, option) from None
        raise


def ask_text(prompt: str, *, option: str = "--yes", **options: Any) -> str:
    """端末で文字を聞く（click.prompt）。答えがないときは ask_confirm と同じ。"""
    try:
        return click.prompt(prompt, err=True, **options)
    except click.exceptions.Abort as abort:
        if _no_input(abort):
            raise confirmation_required(prompt, option) from None
        raise


def execute(
    command: str,
    invocation: Invocation,
    action: Callable[[Invocation], Any],
    render: Callable[[Any], str | None] | None = None,
) -> int:
    invocation.command = command
    try:
        with invocation.holds:
            invocation._hold_workspace()   # use_module がこの前に呼ばれていた場合
            result = action(invocation)
    except WorkError as error:
        return fail(command, invocation, _repository_state(error))
    except (click.exceptions.Exit, click.ClickException, click.exceptions.Abort):
        raise
    except Exception as crash:   # 予期しない誤り（不具合）も、--json なら同じ形の JSON で返す
        if output_closed(crash):
            raise
        return fail(command, invocation, _errors.unexpected(crash))
    _log.logger.debug("%s", command, extra={"event": "command.result", "data": {
        "command": command, "result": to_data(result), "notices": _notices(invocation)}})
    if invocation.json_output:
        for notice in _notices(invocation):
            _events.emit("notice", notice, json_output=True)
        _emit_json(command, invocation, result, None)
    else:
        if render is not None:
            text = render(result)
            if text:
                click.echo(text)
        for notice in _notices(invocation):
            _events.emit("notice", notice, json_output=False)
    return SUCCESS


# GitHub（gh・git）の失敗の出力から、リポジトリがECOBuildの外で変わったことを見分ける
_ARCHIVED = re.compile(r"archived so (?:it )?is read-only|repository was archived", re.IGNORECASE)
_GONE = re.compile(r"repository not found|repository '[^']*' not found|could not resolve to a repository",
                   re.IGNORECASE)


def fail(command: str | None, invocation: Invocation | None, error: WorkError) -> int:
    """失敗の出口：ログに command.error を残し、標準エラーへ誤り（--json ではイベント）、--json なら結果の JSON も。終了コードは1。"""
    log_error(command, error)
    json_output = invocation.json_output if invocation is not None else json_requested
    hint = _errors.hint(error.code, error.hint)
    detail = "" if json_output else _detail_text(error.details)
    _events.emit("error", error.message, json_output=json_output, code=error.code,
                 human=lines(f"エラー：{error.message}", detail, hint and f"ヒント：{hint}"))
    if json_output:
        _emit_json(command, invocation, None, error)
    return FAILURE


def log_error(command: str | None, error: WorkError) -> None:
    """失敗をログに（command.error）。例外の中で呼べば traceback も。"""
    _log.logger.error("%s", error.message, exc_info=sys.exc_info()[0] is not None, extra={
        "event": "command.error", "data": {"command": command, **error_data(error)}})


def error_data(error: WorkError) -> dict:
    """JSON の error（どのコマンドでも同じ形）。"""
    return {"code": error.code, "message": error.message, "hint": _errors.hint(error.code, error.hint),
            "details": to_data(error.details), "retryable": _errors.retryable(error.code)}


def output_closed(error: BaseException) -> bool:
    """出力の先（パイプ）が閉じたための失敗か（| head・読む側が先に終わった。Windows では EINVAL になる）。"""
    if not isinstance(error, OSError) or error.errno not in (errno.EPIPE, errno.EINVAL):
        return False
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (OSError, ValueError):
            return True
    return isinstance(error, BrokenPipeError)


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
    return ([] if module is None else list(module.repository.notices)) + invocation.notices


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


USAGE_HINT = "ecobuild <コマンド> --help で使い方を確認してください。"


def usage_error(message: str, json_output: bool, *, hint: str = USAGE_HINT) -> int:
    """引数の誤り。--json ならJSONで返す（ほかの誤りと同じ形）。ログに command.error を残す。終了コードは2。"""
    error = EcoBuildError(_errors.ErrorCode.USAGE_ERROR, message, hint=hint)
    log_error(attempted, error)
    _events.emit("error", message, json_output=json_output, code=error.code)
    if json_output:
        print_document({"ok": False, "command": attempted, "module": None, "result": None, "notices": [],
                        "error": error_data(error)})
    return USAGE_ERROR


def page(items: list, limit: int, offset: int = 0) -> dict:
    """件数の多い一覧の切り方（--limit・--offset）。{items, total, offset, limit, truncated}。limit が0以下なら全部。"""
    items = list(items)
    offset = max(offset, 0)
    shown = items[offset:] if limit <= 0 else items[offset:offset + limit]
    return {"items": shown, "total": len(items), "offset": offset, "limit": limit,
            "truncated": offset + len(shown) < len(items)}


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


def _emit_json(command: str | None, invocation: Invocation | None, result: Any, error: WorkError | None) -> None:
    module = None if invocation is None else invocation._module
    print_document({
        "ok": error is None,
        "command": command,
        "module": None if module is None else module.root.as_posix(),
        "result": None if error is not None else to_data(result),
        "notices": [] if invocation is None else _notices(invocation),
        "error": None if error is None else error_data(error),
    })


emitted = False      # --json の JSON をもう出したか（予期しない誤りで、2つ目を出さないように）


def print_document(document: dict) -> None:
    """--json の JSON を1つ、標準出力へ。このコマンドのログ（log：{run, file}）を付ける。"""
    global emitted
    emitted = True
    document = {**document, "log": document.get("log", _log.location())}
    click.echo(json.dumps(document, ensure_ascii=False))


def use_utf8_when_redirected() -> None:
    """パイプやファイルへ出すとき（エージェントが読むとき）は、OSの文字コードによらずUTF-8で出す。"""
    for stream in (sys.stdout, sys.stderr):
        if not stream.isatty() and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
