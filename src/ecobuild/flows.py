"""流れ（ecobuild flow）：モジュールの `.ecobuild/flows/<名前>.toml` の定義を、作業空間で実行する（順番・判定・差し戻し・
繰り返し・人の答え待ち・再開）。

状態機械・展開・条件・状態の保存は ecoflow（ECOBuild を知らない）。ここは置き場所と ECOBuild の工程の種類：
- command：コマンドを実行する（args＝引数の配列か run＝シェルの1行。cwd・json・host）。終了コード 0 で済み。
  コンテナにした作業空間ではコンテナの中で動かす（Module.flow_command。拡張が中へ渡す）。このPCで動かすのは host = true
  のときだけ（AI が変えたファイルを、人が見ないままこのPCで動かさないため）。
  AI の値（${steps…}・${vars…}・${out…}）の入れ方を絞る：run・args の先頭・cwd には ${inputs.…}・${run.…} だけ。args の
  先頭がシェル・インタープリター（sh・python 等）なら、ほかの要素にも AI の値を入れない。cwd は作業空間の中だけ。
  args の先頭に .bat・.cmd は使えない（cmd.exe が引数をシェルとして読むため）。
- ecobuild：ecobuild のコマンド（args。--json で呼び、ok で判定。result を out に）。作業空間を消す操作と open は書けない
  （flow run の間は作業空間が使用中。open はこのPCで開く）。AI の値を入れてよいのは文を渡すだけのオプション（TEXT_OPTIONS）
  の値だけ。位置引数・ほかのオプションの値（--x=値・-C値 の形も）は ${inputs.…}・${run.…} だけ。
  host = true の command は、どこにも AI の値を入れられない（ツールは引数1つで別のものを動かせるため）。
- check：ecobuild check（only・tests）。pipeline：パイプラインを1つ走らせる（name）。失敗の出力の末尾を文に入れる。
- approval：人の答えを待つ（message）。ecobuild flow approve／reject で続ける（人がする）。
拡張は Module.flow_kinds を広げて種類を足す（agent は ecobuild_agent）。

置き場所：
- 定義はモジュールで共有する（管理するファイル。変えるのはタスクブランチで）。定義はコードと同じ：エージェントが変えた
  ものは、人が見てから動かす。
- 実行の状態（state.json・ロック・取り消しの印・工程のログ）は作業空間の外（ECOBuild のホームの flows/<作業空間ごとの
  名前>/）。コンテナの中のエージェントが書き換えられないように。名前は作業空間の場所と、作業空間に置いた印
  （${run.dir} の親の .id。作業空間を作り直すと変わる）から作る：同じ場所に作り直した作業空間に前の実行を出さない。
- 失敗した確認の出力は ${run.dir}/<工程>.log にも写す（文には作業空間からの相対の場所。コンテナの中から読める）。
- 作業空間の `.ecobuild/flows/runs/<実行>/` は ${run.dir}：工程（エージェント）が結果の JSON を書く所だけ（git に見せない）。
操作のタイミング（パイプラインの当て方）には当てない：流れは人が flow run で動かすもの。
"""

from __future__ import annotations

import hashlib
import json
import locale
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import ecoflow
from ecoflow import template as _template

from . import config as _config
from . import settings as _settings
from . import workspaces as _workspaces
from .errors import EcoBuildError, ErrorCode
from .fsutil import kill_tree

if TYPE_CHECKING:
    from .module import Module

FLOWS_DIR = f"{_config.DIRECTORY}/flows"
RUNS_DIR = _workspaces.FLOW_RUNS   # 作業空間の中の ${run.dir}（git に見せない）
STATE_HOME = "flows"               # ECOBuild のホームの下：実行の状態の置き場所
SUFFIX = ".toml"
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
MESSAGE_LENGTH = 500   # 工程の文（message）に残す長さ
OUTPUT_IN_MESSAGE = 1500   # 失敗の文に入れる出力の末尾の長さ
OUTPUT_IN_LOG = 2000       # 工程のログに書く出力の末尾の長さ
KILL_WAIT = 10.0           # 時間切れで止めた後、出力を読み切るのを待つ秒数
SAFE_ROOTS = ("inputs", "run")   # run（シェルの1行）・args の先頭・cwd 等に展開してよい名前（人が渡す・ECOBuild が決める）
# args の先頭がこれなら、ほかの要素も AI の値を入れない（引数を中身として読む）
INTERPRETERS = ("cmd", "powershell", "pwsh", "sh", "bash", "zsh", "dash", "fish", "python", "python3", "py", "node",
                "deno", "bun", "perl", "ruby", "php", "wsl", "env", "osascript", "cscript", "wscript")
WORKSPACE_ID = ".id"   # ${run.dir} の親（作業空間の .ecobuild/flows/runs/）に置く印
BATCH = (".bat", ".cmd")
# 流れの中では呼べない ecobuild のコマンド（作業空間を消す。flow run の間は作業空間が使用中で、必ず止まる）
CLOSING = (("task", "finish"), ("task", "drop"), ("task", "prune"), ("task", "close"), ("task", "approve"),
           ("workspace", "close"))
REFUSED = ("open",)   # 流れの中では呼べない ecobuild のコマンド（このPCでファイル・アプリを開く）
# AI の値（steps・vars・out）を入れてよい、文を渡すだけのオプション（ecobuild の CLI の message・note・title・body・
# description・subject・text の引数。ほかのオプションの値と位置引数は inputs・run だけ）
TEXT_OPTIONS = ("--message", "-m", "--note", "--title", "--body", "--description", "--subject", "--text")
# 値を取らないと分かっているオプション（この直後の文のオプションは、そのまま文のオプションとして読む。ほかのオプションの
# 直後なら、そのオプションの値かもしれないので、安全な側に読む）
FLAG_OPTIONS = ("--json", "--yes", "-y", "--no-check", "--draft", "--partial", "--complete", "--start", "--fetch")
STOPPED = ("failed", "cancelled")


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


def workspace_id(root: Path) -> str:
    """作業空間の印（なければ作る）。作業空間を作り直すと消えるので、前の実行と分けられる。"""
    path = Path(root) / RUNS_DIR / WORKSPACE_ID
    try:
        text = path.read_text(encoding="ascii").strip()
        if re.fullmatch(r"[0-9a-f]{12}", text):
            return text
    except (OSError, UnicodeDecodeError):
        pass
    text = uuid.uuid4().hex[:12]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="ascii")
    return text


def state_folder(root: Path) -> Path:
    """作業空間 root の実行の状態の置き場所（ECOBuild のホームの下。作業空間の場所と印ごとの名前）。"""
    digest = hashlib.sha1(_workspaces.key(root).encode("utf-8")).hexdigest()[:12]
    name = re.sub(r"[^A-Za-z0-9_-]", "_", Path(root).name)[:40] or "workspace"
    return _settings.home() / STATE_HOME / f"{name}-{digest}-{workspace_id(root)}"


class _Store(ecoflow.Store):
    """状態は作業空間の外、${run.dir} は作業空間の中（作っておく）。"""

    def __init__(self, root: Path):
        super().__init__(state_folder(root), display=lambda folder: f"{RUNS_DIR}/{folder.name}")
        self.root = Path(root)

    def create(self, flow, values=None, run_id=None):
        run = super().create(flow, values, run_id)
        (self.root / run.state["dir"]).mkdir(parents=True, exist_ok=True)
        return run


class Flows:
    """モジュール（作業空間）の流れ。program：ecobuild の工程で呼ぶ ecobuild（既定は Module.command）。progress：進み具合。"""

    def __init__(self, module: "Module", *, program: tuple[str, ...] = (), progress: Callable[[str], None] | None = None):
        self.module = module
        self.program = tuple(program) or (module.command or "ecobuild",)
        self.engine = ecoflow.Engine(module.flow_kinds(self.program), progress=progress)
        self.store = _Store(module.root)

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
        """実行を作り、人の答え待ちか終わりまで進める（ブロックする）。失敗・取り消しで止まれば flow_failed。"""
        flow = self.load(name)
        return self._do(lambda: self.engine.start(self.store, flow, values or {}), final=True)

    def status(self, run_id: str = "") -> dict:
        """実行の様子（省けば、いちばん新しい実行）。"""
        return self._get(run_id).summary()

    def resume(self, run_id: str) -> dict:
        return self._do(lambda: self.engine.resume(self._get(run_id)), final=True)

    def approve(self, run_id: str, message: str = "") -> dict:
        return self._do(lambda: self.engine.approve(self._get(run_id), message), final=True)

    def reject(self, run_id: str, to: str, message: str) -> dict:
        return self._do(lambda: self.engine.reject(self._get(run_id), to, message), final=True)

    def retry(self, run_id: str) -> dict:
        return self._do(lambda: self.engine.retry(self._get(run_id)), final=True)

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

    def _do(self, action: Callable[[], ecoflow.Run], *, final: bool = False) -> dict:
        try:
            summary = action().summary()
        except ecoflow.FlowError as error:
            raise self._error(error) from error
        if final and summary["status"] in STOPPED:
            raise self._stopped(summary)
        return summary

    def _stopped(self, summary: dict) -> EcoBuildError:
        """失敗・取り消しで止まった実行の誤り（終了コード 1）。"""
        op, run_id = self.module.op, summary["id"]
        current = summary.get("current")
        step = next((s for s in summary["steps"] if s["id"] == current), None)
        where = f"工程 {current} " if current else "最後"
        text = " ".join(str(step.get("message") or "").split())[:MESSAGE_LENGTH] if step else ""
        if summary["status"] == "cancelled":
            message = f"流れ {summary['flow']} の実行 {run_id} は{where}で取り消されました。"
            hint = f"様子は {op('flow status')} {run_id}。もう一度なら {op('flow run')} {summary['flow']}。"
        else:
            message = f"流れ {summary['flow']} の実行 {run_id} は{where}で失敗しました" + (f"：{text}" if text else "。")
            hint = (f"様子は {op('flow status')} {run_id}（工程のログも）。直してから {op('flow retry')} {run_id} で"
                    f"失敗した工程からやり直します。")
        details = {**_brief(summary), "steps": [{"id": s["id"], "status": s["status"], "message": s["message"]}
                                                for s in summary["steps"]]}
        return EcoBuildError(ErrorCode.FLOW_FAILED, message, hint=hint, details=details)

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
                                 hint=f"入力は {op('flow run')} <名前> <入力の名前>=<値> で渡します（入力の一覧は "
                                      f"{op('flow show')} <名前>）。")
        if error.code == ecoflow.ErrorCode.RUN_NOT_FOUND:
            return EcoBuildError(ErrorCode.FLOW_RUN_NOT_FOUND, error.message, hint=f"{op('flow list')} で実行を見られます。")
        if error.code == ecoflow.ErrorCode.RUN_BROKEN:
            return EcoBuildError(ErrorCode.FLOW_RUN_BROKEN, error.message, details=error.details,
                                 hint=f"その実行は続けられません。{op('flow run')} <名前> で始め直してください。")
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
        "command": ecoflow.Kind(lambda step, ctx: _command(module, step, ctx),
                                settings=("run", "args", "cwd", "json", "host"), check=_check_command,
                                description="コマンドを実行する（コンテナの作業空間では中で。host = true ならこのPCで）"),
        "ecobuild": ecoflow.Kind(lambda step, ctx: _ecobuild(module, program, step, ctx), settings=("args",),
                                 required=("args",), check=_check_args, description="ecobuild のコマンド（--json の ok で判定）"),
        "check": ecoflow.Kind(lambda step, ctx: _check(module, step, ctx), settings=("only", "tests"),
                              check=_check_check, description="ecobuild check（only・tests）"),
        "pipeline": ecoflow.Kind(lambda step, ctx: _pipeline(module, step, ctx), settings=("name",), required=("name",),
                                 description="パイプラインを走らせる"),
        "approval": ecoflow.Kind(_approval, settings=("message",), forbid=("pass_if", "retries", "on_fail"),
                                 description="人の答えを待つ（人が flow approve・reject）"),
    }


def _strings(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _batch(program: str) -> bool:
    """先頭が .bat・.cmd（PATH で見つかるものも）か。cmd.exe が引数をシェルとして読むので、AI の値を渡せない。"""
    found = shutil.which(program) or program
    return Path(found).suffix.lower() in BATCH or Path(program).suffix.lower() in BATCH


def _unsafe(text: str) -> list[str]:
    """文の中の、AI の値（inputs・run 以外）の名前。"""
    return [name for name in _template.references(text) if name.split(".")[0] not in SAFE_ROOTS]


def _template_strings(settings: dict) -> list[str]:
    from ecoflow.template import strings
    return strings({key: settings[key] for key in ("run", "args", "cwd") if key in settings})


def _program_name(program: str) -> str:
    name = Path(program.replace("\\", "/")).name.lower()
    for suffix in (".exe", ".com"):
        name = name.removesuffix(suffix)
    return re.sub(r"[0-9.]+$", "", name) if name.startswith("python") else name


def _check_command(settings: dict) -> list[str]:
    has_run, has_args = "run" in settings, "args" in settings
    if has_run == has_args:
        return ["run（シェルの1行）か args（引数の配列）の、どちらか1つを書きます。"]
    problems = []
    if "host" in settings and not isinstance(settings["host"], bool):
        problems.append("host は真偽です（true でこのPCで動かします）。")
    if "cwd" in settings:
        if not isinstance(settings["cwd"], str):
            problems.append("cwd は文字列です。")
        elif _unsafe(settings["cwd"]):
            problems.append(f"cwd に展開してよいのは ${{inputs.…}}・${{run.…}} だけです（{'・'.join(_unsafe(settings['cwd']))}）。")
    if settings.get("host") is True:   # このPCで動かすものは、どこにも AI の値を入れない
        bad = [name for text in _template_strings(settings) for name in _unsafe(text)]
        if bad:
            return [*problems, f"host = true（このPCで動かす）の工程には、工程・エージェントの値（{'・'.join(bad)}）を"
                               "入れられません（ツールは引数1つで別のものを動かせます）。値は ${run.dir} のファイルで渡します。"]
    if has_run:
        if not isinstance(settings["run"], str):
            return [*problems, "run は文字列です。"]
        if _unsafe(settings["run"]):
            problems.append(f"run（シェルの1行）に展開してよいのは ${{inputs.…}}・${{run.…}} だけです"
                            f"（{'・'.join(_unsafe(settings['run']))}）。工程・エージェントの値はシェルに入れません：args（引数の配列）を使います。")
        return problems
    if not _strings(settings["args"]) or not settings["args"]:
        return [*problems, "args は文字列の配列です。"]
    first, rest = settings["args"][0], settings["args"][1:]
    if _unsafe(first):
        problems.append(f"args の先頭（実行するもの）に展開してよいのは ${{inputs.…}}・${{run.…}} だけです（{'・'.join(_unsafe(first))}）。")
    elif "${" not in first and _batch(first):
        problems.append(f"args の先頭に .bat・.cmd（{first}）は使えません（引数がシェルとして読まれます）。")
    elif _program_name(first) in INTERPRETERS:
        bad = [name for text in rest for name in _unsafe(text)]
        if bad:
            problems.append(f"args の先頭が {first}（シェル・インタープリター）なので、ほかの要素にも工程・エージェントの値"
                            f"（{'・'.join(bad)}）は入れられません（中身として動いてしまいます）。値はファイル（${{run.dir}}）で渡します。")
    return problems


def _head(args: list[str]) -> tuple[list[str], list[str]]:
    """(コマンドの名前の部分, -C・--directory の値)。名前は頭のオプションでない語（コマンドの前のオプションは飛ばし、
    名前の後のオプションで終わる）。"""
    words, places, at = [], [], 0
    while at < len(args):
        arg = args[at]
        if arg in ("-C", "--directory"):
            places.append(args[at + 1] if at + 1 < len(args) else "")
            at += 2
            continue
        if arg.startswith("--directory=") or (arg.startswith("-C") and not arg.startswith("--") and len(arg) > 2):
            places.append(arg.split("=", 1)[1] if arg.startswith("--") else arg[2:])
            at += 1
            continue
        if arg.startswith("-"):
            if words:
                break
        else:
            words.append(arg)
        at += 1
    return words, places


def _words(args: list[str]) -> tuple[str, ...]:
    return tuple(_head(args)[0][:2])


def _unsafe_args(args: list[str]) -> list[str]:
    """AI の値を入れてはいけない所にある AI の値の名前。許すのは文のオプション（TEXT_OPTIONS）の値だけ
    （--message 値・--message=値）。ほか（位置引数・オプションの名前・ほかのオプションの値）はすべて inputs・run だけ。
    `--` の後ろは全部が引数（inputs・run だけ）。文のオプションの名前でも、直前が値を取るかもしれないオプション
    （FLAG_OPTIONS にない名前）なら、その値かもしれないので文のオプションとして読まない。"""
    bad, at, after_option = [], 0, False
    while at < len(args):
        arg = args[at]
        if arg == "--":
            bad += [name for rest in args[at + 1:] for name in _unsafe(rest)]
            break
        name, sep, _ = arg.partition("=")
        if not after_option and (arg in TEXT_OPTIONS or (sep and name.startswith("--") and name in TEXT_OPTIONS)):
            at += 1 if sep else 2   # 次（か = の後ろ）は文の値
            continue
        bad += _unsafe(arg)
        after_option = arg.startswith("-") and not sep and arg not in FLAG_OPTIONS
        at += 1
    return bad


def _refusal(args: list[str]) -> str | None:
    words = _words(args)
    if words in CLOSING:
        return (f"流れの中では作業空間を消す操作（ecobuild {' '.join(words)}）はできません"
                "（流れの間は作業空間が使用中です。流れが終わってから人がします）。")
    if words[:1] and words[0] in REFUSED:
        return f"流れの中では ecobuild {words[0]} はできません（このPCでファイル・アプリを開くため）。"
    return None


def _check_args(settings: dict) -> list[str]:
    if not _strings(settings.get("args")) or not settings["args"]:
        return ["args は文字列の配列です（例：[\"task\", \"status\"]）。"]
    problems = []
    bad = _unsafe_args(settings["args"])
    if bad:
        problems.append(f"工程・エージェントの値（{'・'.join(bad)}）を入れてよいのは、文を渡すオプション（"
                        f"{'・'.join(TEXT_OPTIONS)}）の値だけです。位置引数・ほかのオプションの値は ${{inputs.…}}・${{run.…}} だけです。")
    refusal = _refusal(settings["args"])
    if refusal:
        problems.append(refusal)
    return problems


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


def _text(value) -> str:
    """出力を文に（UTF-8 で読めなければ、このPCの既定の文字コード。Windows の多くのコマンドは cp932）。"""
    if not isinstance(value, bytes):
        return value or ""
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.decode(locale.getpreferredencoding(False), "replace")


def _kill_group(process: subprocess.Popen) -> None:
    """プロセスを子・孫ごと止める（Windows は taskkill /T、ほかはプロセスグループ）。"""
    if os.name == "nt":
        kill_tree(process.pid)
        return
    import signal
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        pass


def _execute(command, ctx, *, cwd: Path, shell: bool = False, env: dict | None = None,
             stop: Callable[[], None] | None = None) -> subprocess.CompletedProcess | ecoflow.Outcome:
    """コマンドを実行し、出力をその工程のログに書く。出力は一時ファイルに受ける（残った孫がパイプを持っていても、親が
    終われば戻る）。時間切れ・中断（Ctrl+C）なら子・孫ごと止め（stop：コンテナの中のプロセスも止める口）、終わった後も
    プロセスグループを片付ける。始められない・時間切れなら失敗の Outcome。"""
    shown = command if isinstance(command, str) else " ".join(command)
    ctx.log(f"$ {shown}")
    group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True})
    with tempfile.TemporaryFile() as out_file, tempfile.TemporaryFile() as err_file:
        try:
            process = subprocess.Popen(command, shell=shell, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out_file,
                                       stderr=err_file, **group)
        except OSError as error:
            return ecoflow.Outcome(ecoflow.FAILED, f"コマンドを実行できません：{error}")
        timed_out = False
        try:
            process.wait(timeout=ctx.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _stop_all(process, stop)
            try:
                process.wait(timeout=KILL_WAIT)
            except subprocess.TimeoutExpired:
                process.kill()
        except BaseException:
            _stop_all(process, stop)
            raise
        if not timed_out:   # 親が終わった後に残った孫（POSIX はプロセスグループ、コンテナは印の付いた中のプロセス）
            if os.name != "nt":
                _kill_group(process)
            if stop is not None:
                try:
                    stop()
                except Exception:
                    pass
        stdout, stderr = (_read_back(f) for f in (out_file, err_file))
    if timed_out:
        ctx.log(stdout + stderr + "（時間切れで止めました）")
        return ecoflow.Outcome(ecoflow.FAILED, f"{int(ctx.timeout or 0)} 秒で終わりませんでした。")
    done = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    ctx.log(done.stdout + done.stderr + f"（終了コード {done.returncode}）")
    return done


def _read_back(file) -> str:
    file.seek(0)
    return _text(file.read())


def _stop_all(process: subprocess.Popen, stop: Callable[[], None] | None) -> None:
    _kill_group(process)
    if stop is not None:
        try:
            stop()
        except Exception:   # 中のプロセスを止められなくても、このPCの側は止めた
            pass


def _command(module: "Module", step, ctx) -> ecoflow.Outcome:
    shell_line = ctx.setting("run")
    host = ctx.setting("host", False) is True
    if shell_line is not None:
        command = shell_line
    else:
        command = [str(a) for a in ctx.setting("args")]
        if _batch(command[0]):
            return ecoflow.Outcome(ecoflow.FAILED, f"args の先頭に .bat・.cmd（{command[0]}）は使えません。")
    cwd = (Path(module.root) / str(ctx.setting("cwd", "."))).resolve()
    if cwd != Path(module.root).resolve() and Path(module.root).resolve() not in cwd.parents:
        return ecoflow.Outcome(ecoflow.FAILED, f"cwd（{ctx.setting('cwd')}）が作業空間の外です。")
    shell, env, stop = shell_line is not None, None, None
    if not host:   # コンテナにした作業空間なら中で（拡張が渡す）
        command, env, shell, stop = module.flow_command(command, cwd=cwd, shell=shell, progress=ctx.progress)
    done = _execute(command, ctx, cwd=cwd, shell=shell, env=env, stop=stop)
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
    if args and _batch(program[0]):
        return ecoflow.Outcome(ecoflow.FAILED, f"ecobuild（{program[0]}）が .bat・.cmd なので、流れからは呼べません。")
    if _refusal(args):
        return ecoflow.Outcome(ecoflow.FAILED, _refusal(args))
    if "--json" not in args:   # -- より後ろは引数（--json はその前に）
        at = args.index("--") if "--" in args else len(args)
        args = [*args[:at], "--json", *args[at:]]
    done = _execute([*program, *args], ctx, cwd=module.root)
    shown = " ".join(a for a in args if a != "--json")
    if isinstance(done, ecoflow.Outcome):
        return done
    document = _json_line(done.stdout or "")
    if not isinstance(document, dict):
        return ecoflow.Outcome(ecoflow.FAILED, f"ecobuild {shown} の結果（JSON）が読めません（終了コード {done.returncode}）。")
    if document.get("ok"):
        result = document.get("result")
        return ecoflow.Outcome(ecoflow.DONE, f"ecobuild {shown} が通りました",
                               out=result if isinstance(result, dict) else {"result": result})
    error = document.get("error") if isinstance(document.get("error"), dict) else {}
    return ecoflow.Outcome(ecoflow.FAILED, _short(str(error.get("message") or f"ecobuild {shown} が失敗しました。")),
                           out={"error": error})


def _items_outcome(items: list[dict], ctx, failed_head: str, done_message: str,
                   root: Path | None = None) -> ecoflow.Outcome:
    """確認の項目から結果を作る。失敗した項目の出力の末尾を、工程のログと作業空間の ${run.dir}/<工程>.log（コンテナの
    中から読める）に書き、文には末尾と作業空間からの相対の場所を入れる（直す側が読めるように）。"""
    from .module import CHECK_NAMES
    tails, copied = [], []
    for item in items:
        ctx.log(f"{'OK' if item['ok'] else 'NG'} {CHECK_NAMES.get(item['name'], item['name'])} {item.get('detail') or ''}")
        if not item["ok"] and item.get("output"):
            text = f"--- {item['name']} の出力の末尾 ---\n{item['output'][-OUTPUT_IN_LOG:]}"
            ctx.log(text)
            copied.append(text)
            tails.append(item["output"])
    where = f"{ctx.dir}/{ctx.step.id}.log"
    if copied and root is not None:
        try:
            (Path(root) / where).parent.mkdir(parents=True, exist_ok=True)
            (Path(root) / where).write_text("\n".join(copied) + "\n", encoding="utf-8")
        except OSError:
            copied = []
    out = {"items": [{k: v for k, v in item.items() if k != "output"} for item in items]}
    failed = [i for i in items if not i["ok"]]
    if not failed:
        return ecoflow.Outcome(ecoflow.DONE, done_message, out=out)
    summary = _short(failed_head + "、".join(
        CHECK_NAMES.get(i["name"], i["name"]) + (f"：{i['detail']}" if i.get("detail") else "") for i in failed))
    message = summary + (f"（出力：{where}）" if copied and root is not None else "")
    if tails:
        message += "\n出力の末尾：\n" + "\n".join(tails)[-OUTPUT_IN_MESSAGE:]
    return ecoflow.Outcome(ecoflow.FAILED, message, out=out)


def _check(module: "Module", step, ctx) -> ecoflow.Outcome:
    only = ctx.setting("only")
    tests = tuple(ctx.setting("tests", []) or ())
    try:
        items = [{"name": i.name, "ok": i.ok, "detail": i.detail, "output": i.output}
                 for i in module.check(only=tuple(only) if only is not None else None, tests=tests).items]
    except EcoBuildError as error:
        if error.code != ErrorCode.CHECK_FAILED or not isinstance(error.details, list):
            ctx.log(error.message)
            return ecoflow.Outcome(ecoflow.FAILED, _short(error.message))
        items = [dict(item) for item in error.details]
    return _items_outcome(items, ctx, "", "確認が通りました", module.root)


def _pipeline(module: "Module", step, ctx) -> ecoflow.Outcome:
    name = str(ctx.setting("name"))
    try:
        run = module.run_pipeline(name, progress=ctx.progress)
    except EcoBuildError as error:
        return ecoflow.Outcome(ecoflow.FAILED, _short(error.message))
    items = [{"name": i.name, "ok": i.ok, "detail": i.detail, "output": i.output} for i in run.items]
    return _items_outcome(items, ctx, f"パイプライン {name} が失敗しました：", f"パイプライン {name} が通りました",
                          module.root)


def _approval(step, ctx) -> ecoflow.Outcome:
    return ecoflow.Outcome(ecoflow.WAITING, str(ctx.setting("message", "") or "確かめてください"))
