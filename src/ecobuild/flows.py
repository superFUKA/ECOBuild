"""流れ（ecobuild flow）：モジュールの `.ecobuild/flows/<名前>.toml` の定義を、作業空間の `.ecobuild/flows/runs/<実行>/`
で実行する（順番・判定・差し戻し・繰り返し・人の答え待ち・再開）。

状態機械・展開・条件・状態の保存は ecoflow（ECOBuild を知らない）。ここは置き場所と ECOBuild の工程の種類：
- command：コマンドを実行する（run＝シェルの1行か args＝引数の配列。cwd・json）。終了コード 0 で済み。
- ecobuild：ecobuild のコマンド（args。--json で呼び、ok で判定。result を out に）。
- check：ecobuild check（only・tests）。
- pipeline：パイプラインを1つ走らせる（name）。
- approval：人の答えを待つ（message）。ecobuild flow approve／reject で続ける。
拡張は Module.flow_kinds を広げて種類を足す（agent は ecobuild_agent）。

定義はモジュールで共有する（管理するファイル。変えるのはタスクブランチで）。実行の置き場所は git に見せない
（workspaces.exclude_area）。操作のタイミング（パイプラインの当て方）には当てない：流れは人が flow run で動かすもの。
"""

from __future__ import annotations

import json
import locale
import re
import subprocess
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import ecoflow

from . import config as _config
from . import workspaces as _workspaces
from .errors import EcoBuildError, ErrorCode

if TYPE_CHECKING:
    from .module import Module

FLOWS_DIR = f"{_config.DIRECTORY}/flows"
RUNS_DIR = _workspaces.FLOW_RUNS   # 実行の置き場所（git に見せない）
SUFFIX = ".toml"
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
MESSAGE_LENGTH = 500   # 工程の文（message）に残す長さ


@dataclass(frozen=True)
class FlowEntry:
    """定義1つ（flow list）。error：読めない・誤りがあるときの文。"""
    name: str
    path: str
    description: str
    steps: tuple[str, ...]
    error: str | None = None


@dataclass(frozen=True)
class FlowList:
    flows: tuple[FlowEntry, ...]
    runs: tuple[dict, ...]       # この作業空間の実行（作った順。ecoflow.Run.summary の頭の項目）


@dataclass(frozen=True)
class FlowShown:
    """定義（flow show）：読み込んだ形と確かめ（problems が空なら使える）。"""
    name: str
    path: str
    description: str
    inputs: tuple[dict, ...]
    steps: tuple[dict, ...]
    problems: tuple[str, ...]
    kinds: tuple[str, ...]


class Flows:
    """モジュール（作業空間）の流れ。program：ecobuild の工程で呼ぶ ecobuild（既定は Module.command）。progress：進み具合。"""

    def __init__(self, module: "Module", *, program: tuple[str, ...] = (), progress: Callable[[str], None] | None = None):
        self.module = module
        self.program = tuple(program) or (module.command or "ecobuild",)
        self.engine = ecoflow.Engine(module.flow_kinds(self.program), progress=progress)
        root = module.root
        self.store = ecoflow.Store(root / RUNS_DIR, display=lambda folder: folder.relative_to(root).as_posix())

    @property
    def folder(self) -> Path:
        return self.module.root / FLOWS_DIR

    def path(self, name: str) -> Path:
        return self.folder / f"{name}{SUFFIX}"

    # ---- 定義 -------------------------------------------------------------------------------------------
    def names(self) -> list[str]:
        if not self.folder.is_dir():
            return []
        return sorted(p.stem for p in self.folder.glob(f"*{SUFFIX}") if p.is_file() and _NAME.match(p.stem))

    def _read(self, name: str) -> dict:
        if not _NAME.match(name or ""):
            raise EcoBuildError(ErrorCode.FLOW_NOT_FOUND, f"流れの名前「{name}」は使えません（英数字・_・-）。",
                                hint=self._list_hint())
        path = self.path(name)
        if not path.is_file():
            raise EcoBuildError(ErrorCode.FLOW_NOT_FOUND, f"流れ {name} はありません（{FLOWS_DIR}/{name}{SUFFIX}）。",
                                hint=self._list_hint())
        try:
            return tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
            raise EcoBuildError(ErrorCode.INVALID_FLOW, f"{FLOWS_DIR}/{name}{SUFFIX} が読めません：{error}",
                                hint="TOML の書き方を直してください。") from error

    def load(self, name: str) -> ecoflow.Flow:
        """定義を読んで確かめる（誤りがあれば invalid_flow）。"""
        try:
            return ecoflow.load(self._read(name), name, self.engine.kinds)
        except ecoflow.FlowError as error:
            raise self._error(error) from error

    def list(self) -> FlowList:
        entries = []
        for name in self.names():
            try:
                flow = self.load(name)
                entries.append(FlowEntry(name, f"{FLOWS_DIR}/{name}{SUFFIX}", flow.description,
                                         tuple(s.id for s in flow.steps)))
            except EcoBuildError as error:
                entries.append(FlowEntry(name, f"{FLOWS_DIR}/{name}{SUFFIX}", "", (), error.message))
        runs = tuple(_brief(run.summary()) for run in self.store.runs())
        return FlowList(tuple(entries), runs)

    def show(self, name: str) -> FlowShown:
        data = self._read(name)
        flow, problems = ecoflow.check(data, name, self.engine.kinds)
        steps = data.get("steps") if isinstance(data.get("steps"), list) else []
        inputs = data.get("inputs") if isinstance(data.get("inputs"), dict) else {}
        shown_inputs = tuple({"name": key, **(value if isinstance(value, dict) else {"help": value})}
                             for key, value in inputs.items())
        return FlowShown(name, f"{FLOWS_DIR}/{name}{SUFFIX}", str(data.get("description", "")), shown_inputs,
                         tuple(s for s in steps if isinstance(s, dict)), tuple(problems), tuple(sorted(self.engine.kinds)))

    # ---- 実行 -------------------------------------------------------------------------------------------
    def run(self, name: str, values: dict[str, Any] | None = None) -> dict:
        """実行を作り、人の答え待ちか終わり・失敗まで進める（ブロックする）。"""
        flow = self.load(name)
        return self._do(lambda: self.engine.start(self.store, flow, values or {}))

    def status(self, run_id: str = "") -> dict:
        """実行の様子（省けば、いちばん新しい実行）。"""
        return self._get(run_id).summary()

    def resume(self, run_id: str) -> dict:
        return self._do(lambda: self.engine.resume(self._get(run_id)))

    def approve(self, run_id: str, message: str = "") -> dict:
        return self._do(lambda: self.engine.approve(self._get(run_id), message))

    def reject(self, run_id: str, to: str, message: str) -> dict:
        return self._do(lambda: self.engine.reject(self._get(run_id), to, message))

    def retry(self, run_id: str) -> dict:
        return self._do(lambda: self.engine.retry(self._get(run_id)))

    def cancel(self, run_id: str) -> dict:
        return self._do(lambda: self.engine.cancel(self._get(run_id)))

    def _get(self, run_id: str) -> ecoflow.Run:
        try:
            if not run_id:
                latest = self.store.latest()
                if latest is None:
                    raise EcoBuildError(ErrorCode.FLOW_RUN_NOT_FOUND, "この作業空間には、流れの実行がありません。",
                                        hint=f"{self.module.op('flow run')} <名前> で始めます（定義は {self.module.op('flow list')}）。")
                return latest
            return self.store.get(run_id)
        except ecoflow.FlowError as error:
            raise self._error(error) from error

    def _do(self, action: Callable[[], ecoflow.Run]) -> dict:
        try:
            return action().summary()
        except ecoflow.FlowError as error:
            raise self._error(error) from error

    def _list_hint(self) -> str:
        return f"{self.module.op('flow list')} で定義を見られます（定義は {FLOWS_DIR}/<名前>{SUFFIX}）。"

    def _error(self, error: ecoflow.FlowError) -> EcoBuildError:
        """ecoflow の誤りを ECOBuild の誤りに（ヒントは ECOBuild のコマンドで）。"""
        op = self.module.op
        if error.code == ecoflow.ErrorCode.INVALID_FLOW:
            return EcoBuildError(ErrorCode.INVALID_FLOW, error.message, details=error.details,
                                 hint=f"定義（{FLOWS_DIR}/<名前>{SUFFIX}）を直してください（{op('flow show')} <名前> で確かめられます）。")
        if error.code == ecoflow.ErrorCode.INVALID_INPUT:
            return EcoBuildError(ErrorCode.INVALID_ARGUMENT, error.message, details=error.details,
                                 hint=f"入力は --set <名前>=<値> で渡します（入力の一覧は {op('flow show')} <名前>）。")
        if error.code == ecoflow.ErrorCode.RUN_NOT_FOUND:
            return EcoBuildError(ErrorCode.FLOW_RUN_NOT_FOUND, error.message, hint=f"{op('flow list')} で実行を見られます。")
        if error.code == ecoflow.ErrorCode.RUN_LOCKED:
            return EcoBuildError(ErrorCode.FLOW_RUN_LOCKED, error.message, details=error.details,
                                 hint=f"動いている実行が終わるのを待つか、{op('flow cancel')} <実行> で止めてください。")
        details = error.details if isinstance(error.details, dict) else {}
        actions = details.get("actions") or []
        hint = ("次にできること：" + "・".join(f"{op('flow ' + a)} <実行>" for a in actions)) if actions else None
        return EcoBuildError(ErrorCode.FLOW_RUN_STATE, error.message, hint=hint, details=details)


def _brief(summary: dict) -> dict:
    return {key: summary[key] for key in ("id", "flow", "status", "current", "created", "updated")}


# ---- ECOBuild の工程の種類 -------------------------------------------------------------------------------
def kinds(module: "Module", program: tuple[str, ...]) -> dict[str, ecoflow.Kind]:
    return {
        "command": ecoflow.Kind(lambda step, ctx: _command(module, step, ctx), settings=("run", "args", "cwd", "json"),
                                check=_check_command, description="コマンドを実行する（終了コード 0 で済み）"),
        "ecobuild": ecoflow.Kind(lambda step, ctx: _ecobuild(module, program, step, ctx), settings=("args",),
                                 required=("args",), check=_check_args, description="ecobuild のコマンド（--json の ok で判定）"),
        "check": ecoflow.Kind(lambda step, ctx: _check(module, step, ctx), settings=("only", "tests"),
                              check=_check_check, description="ecobuild check（only・tests）"),
        "pipeline": ecoflow.Kind(lambda step, ctx: _pipeline(module, step, ctx), settings=("name",), required=("name",),
                                 description="パイプラインを走らせる"),
        "approval": ecoflow.Kind(_approval, settings=("message",), description="人の答えを待つ（flow approve・reject）"),
    }


def _strings(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _check_command(settings: dict) -> list[str]:
    has_run, has_args = "run" in settings, "args" in settings
    if has_run == has_args:
        return ["run（シェルの1行）か args（引数の配列）の、どちらか1つを書きます。"]
    if has_run and not isinstance(settings["run"], str):
        return ["run は文字列です。"]
    if has_args and (not _strings(settings["args"]) or not settings["args"]):
        return ["args は文字列の配列です。"]
    return []


def _check_args(settings: dict) -> list[str]:
    return [] if _strings(settings.get("args")) and settings["args"] else ["args は文字列の配列です（例：[\"task\", \"status\"]）。"]


def _check_check(settings: dict) -> list[str]:
    for key in ("only", "tests"):
        if key in settings and not _strings(settings[key]):
            return [f"{key} は文字列の配列です。"]
    if "only" in settings:
        try:
            _config.validate_steps(tuple(settings["only"]))
        except EcoBuildError as error:
            return [f"only：{error.message}"]
    return []


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MESSAGE_LENGTH else text[:MESSAGE_LENGTH] + "…"


def _last_line(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-1].strip() if lines else ""


def _json_line(text: str):
    try:
        return json.loads(_last_line(text))
    except ValueError:
        return None


def _execute(command, ctx, *, cwd: Path, shell: bool = False) -> subprocess.CompletedProcess | ecoflow.Outcome:
    """コマンドを実行し、出力をその工程のログに書く。始められない・時間切れなら失敗の Outcome。"""
    ctx.log(f"$ {command if isinstance(command, str) else ' '.join(command)}")
    try:
        done = subprocess.run(command, shell=shell, cwd=cwd, capture_output=True, timeout=ctx.timeout,
                              stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired as expired:
        ctx.log(_text(expired.stdout) + _text(expired.stderr))
        return ecoflow.Outcome(ecoflow.FAILED, f"{int(ctx.timeout or 0)} 秒で終わりませんでした。")
    except OSError as error:
        return ecoflow.Outcome(ecoflow.FAILED, f"コマンドを実行できません：{error}")
    done = subprocess.CompletedProcess(done.args, done.returncode, _text(done.stdout), _text(done.stderr))
    ctx.log(done.stdout + done.stderr + f"（終了コード {done.returncode}）")
    return done


def _text(value) -> str:
    """出力を文に（UTF-8 で読めなければ、このPCの既定の文字コード。Windows の多くのコマンドは cp932）。"""
    if not isinstance(value, bytes):
        return value or ""
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.decode(locale.getpreferredencoding(False), "replace")


def _command(module: "Module", step, ctx) -> ecoflow.Outcome:
    shell_line = ctx.setting("run")
    command = shell_line if shell_line is not None else [str(a) for a in ctx.setting("args")]
    done = _execute(command, ctx, cwd=module.root / str(ctx.setting("cwd", ".")), shell=shell_line is not None)
    if isinstance(done, ecoflow.Outcome):
        return done
    out: dict = {"exit_code": done.returncode}
    if ctx.setting("json", False):
        document = _json_line(done.stdout or "")
        if isinstance(document, dict):
            out.update(document)
    message = _short(str(out.get("message") or "") or _last_line(done.stdout or "") or _last_line(done.stderr or ""))
    if done.returncode != 0:
        return ecoflow.Outcome(ecoflow.FAILED, f"終了コード {done.returncode}" + (f"：{message}" if message else ""), out=out)
    if out.get("ok") is False:
        return ecoflow.Outcome(ecoflow.FAILED, message or "結果が ok: false です。", out=out)
    return ecoflow.Outcome(ecoflow.DONE, message, out=out)


def _ecobuild(module: "Module", program: tuple[str, ...], step, ctx) -> ecoflow.Outcome:
    args = [str(a) for a in ctx.setting("args")]
    command = [*program, *args, *([] if "--json" in args else ["--json"])]
    done = _execute(command, ctx, cwd=module.root)
    if isinstance(done, ecoflow.Outcome):
        return done
    document = _json_line(done.stdout or "")
    if not isinstance(document, dict):
        return ecoflow.Outcome(ecoflow.FAILED, f"ecobuild {' '.join(args)} の結果（JSON）が読めません（終了コード {done.returncode}）。")
    if document.get("ok"):
        result = document.get("result")
        return ecoflow.Outcome(ecoflow.DONE, f"ecobuild {' '.join(args)} が通りました",
                               out=result if isinstance(result, dict) else {"result": result})
    error = document.get("error") if isinstance(document.get("error"), dict) else {}
    return ecoflow.Outcome(ecoflow.FAILED, _short(str(error.get("message") or f"ecobuild {' '.join(args)} が失敗しました。")),
                           out={"error": error})


def _check(module: "Module", step, ctx) -> ecoflow.Outcome:
    from .module import CHECK_NAMES
    only = ctx.setting("only")
    tests = tuple(ctx.setting("tests", []) or ())
    try:
        items = [{"name": i.name, "ok": i.ok, "detail": i.detail}
                 for i in module.check(only=tuple(only) if only is not None else None, tests=tests).items]
    except EcoBuildError as error:
        if error.code != ErrorCode.CHECK_FAILED or not isinstance(error.details, list):
            ctx.log(error.message)
            return ecoflow.Outcome(ecoflow.FAILED, _short(error.message))
        items = [dict(item) for item in error.details]
    for item in items:
        ctx.log(f"{'OK' if item['ok'] else 'NG'} {CHECK_NAMES.get(item['name'], item['name'])} {item.get('detail') or ''}")
    failed = [i for i in items if not i["ok"]]
    if failed:
        return ecoflow.Outcome(ecoflow.FAILED, _short("、".join(
            CHECK_NAMES.get(i["name"], i["name"]) + (f"：{i['detail']}" if i.get("detail") else "") for i in failed)),
            out={"items": items})
    return ecoflow.Outcome(ecoflow.DONE, "確認が通りました", out={"items": items})


def _pipeline(module: "Module", step, ctx) -> ecoflow.Outcome:
    name = str(ctx.setting("name"))
    try:
        run = module.run_pipeline(name, progress=ctx.progress)
    except EcoBuildError as error:
        return ecoflow.Outcome(ecoflow.FAILED, _short(error.message))
    items = [{"name": i.name, "ok": i.ok, "detail": i.detail} for i in run.items]
    failed = [i for i in items if not i["ok"]]
    if failed:
        return ecoflow.Outcome(ecoflow.FAILED, _short(f"パイプライン {name} が失敗しました：" + "、".join(
            i["name"] + (f"（{i['detail']}）" if i["detail"] else "") for i in failed)), out={"items": items})
    return ecoflow.Outcome(ecoflow.DONE, f"パイプライン {name} が通りました", out={"items": items})


def _approval(step, ctx) -> ecoflow.Outcome:
    return ecoflow.Outcome(ecoflow.WAITING, str(ctx.setting("message", "") or "確かめてください"))
