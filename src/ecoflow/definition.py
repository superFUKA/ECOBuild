"""流れの定義：dict（TOML 等を読んだもの）から読み、確かめる。工程の種類（Kind）の決まりもここ。

    description = "…"
    [inputs]
    goal = { help = "…", required = true }      # または goal = "説明"
    [[steps]]
    id = "impl"            # 英数字・_・-（重複なし）
    type = "agent"         # 工程の種類（利用側が登録する）
    when = "…"             # 条件が偽なら飛ばす
    pass_if = "…"          # 終わった後の判定（偽なら失敗）
    on_fail = { to = "impl", max = 3, message = "…" }   # 失敗したら to へ戻る（max 回まで。message は ${vars.feedback}）
    loop = { to = "impl", max = 3, until = "…" }        # 終わった後、until が偽なら to へ戻る（max 回まで）
    retries = 1            # 失敗したら、同じ工程をそのままやり直す回数（既定 0）
    timeout = 600          # 秒（種類が使う）
    …                      # ほかは種類の設定
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from . import template as _expand
from .errors import ErrorCode, FlowError

COMMON_KEYS = ("id", "type", "when", "pass_if", "on_fail", "loop", "retries", "timeout")
MAX_BACKS = 10
MAX_RETRIES = 10
_ID = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class Back:
    """差し戻し（on_fail）・繰り返し（loop）の行き先と回数。"""
    to: str
    max: int
    message: str = ""     # on_fail：${vars.feedback} にする文（空なら失敗の文）
    until: str = ""       # loop：真になったら繰り返さない（空なら max 回まで繰り返す）


@dataclass(frozen=True)
class Input:
    name: str
    help: str = ""
    required: bool = False
    default: Any = None


@dataclass(frozen=True)
class Step:
    id: str
    type: str
    when: str = ""
    pass_if: str = ""
    on_fail: Back | None = None
    loop: Back | None = None
    retries: int = 0
    timeout: float | None = None
    settings: dict = field(default_factory=dict)   # 種類の設定（展開する前）


@dataclass(frozen=True)
class Flow:
    name: str
    description: str
    inputs: tuple[Input, ...]
    steps: tuple[Step, ...]
    data: dict = field(default_factory=dict)   # 読んだ元（実行に写しを残す）

    def index(self, step_id: str) -> int:
        for number, step in enumerate(self.steps):
            if step.id == step_id:
                return number
        raise KeyError(step_id)

    def step(self, step_id: str) -> Step:
        return self.steps[self.index(step_id)]

    def after(self, step_id: str) -> str | None:
        """次の工程（最後なら None）。"""
        number = self.index(step_id) + 1
        return self.steps[number].id if number < len(self.steps) else None


@dataclass(frozen=True)
class Outcome:
    """工程の結果。status：done・failed・waiting。out：工程の出力（JSON の dict）。vars：実行の vars に足すもの。"""
    status: str
    message: str = ""
    vars: dict = field(default_factory=dict)
    out: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Kind:
    """工程の種類。run(step, ctx) → Outcome。settings：書ける設定の名前（None なら確かめない）。required：必須の設定。
    check(settings) → 誤りの文の一覧（任意）。"""
    run: Callable[..., Outcome]
    settings: tuple[str, ...] | None = None
    required: tuple[str, ...] = ()
    check: Callable[[dict], list[str]] | None = None
    description: str = ""


def as_kind(value) -> Kind:
    """登録したもの（Kind か関数）を Kind に。"""
    return value if isinstance(value, Kind) else Kind(run=value)


def load(data: Mapping, name: str, kinds: Mapping | None = None) -> Flow:
    """定義を読む。誤りがあれば INVALID_FLOW（details に誤りの一覧）。kinds：登録した種類（None なら種類を確かめない）。"""
    flow, problems = check(data, name, kinds)
    if problems:
        raise FlowError(ErrorCode.INVALID_FLOW, f"流れ {name} の定義に誤りがあります：" + "／".join(problems),
                        details=problems)
    return flow


def check(data: Mapping, name: str, kinds: Mapping | None = None) -> tuple[Flow | None, list[str]]:
    """定義を読み、(Flow, 誤りの一覧) を返す（誤りがあれば Flow は None）。"""
    problems: list[str] = []
    if not isinstance(data, Mapping):
        return None, ["定義は表（dict）です。"]
    unknown = sorted(set(data) - {"description", "inputs", "steps"})
    if unknown:
        problems.append(f"知らない項目があります：{', '.join(unknown)}")
    description = data.get("description", "")
    if not isinstance(description, str):
        problems.append("description は文字列です。")
        description = ""
    inputs = _inputs(data.get("inputs", {}), problems)
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        problems.append("steps（[[steps]]）が1つもありません。")
        raw_steps = []
    steps: list[Step] = []
    seen: set[str] = set()
    for number, raw in enumerate(raw_steps, 1):
        step = _step(raw, number, seen, kinds, problems)
        if step is not None:
            seen.add(step.id)
            steps.append(step)
    ids = [s.id for s in steps]
    for position, step in enumerate(steps):
        for label, back in (("on_fail", step.on_fail), ("loop", step.loop)):
            if back is not None and back.to not in ids[:position + 1]:
                problems.append(f"工程 {step.id} の {label}.to「{back.to}」は、自分か前の工程ではありません。")
        _check_references(step, ids, problems)
    if problems:
        return None, problems
    return Flow(name, description, tuple(inputs), tuple(steps), dict(data)), []


def _inputs(raw, problems: list[str]) -> list[Input]:
    if not isinstance(raw, Mapping):
        problems.append("inputs は表です。")
        return []
    found = []
    for name, value in raw.items():
        if not _ID.match(str(name)):
            problems.append(f"入力の名前「{name}」は英数字・_・- で書きます。")
            continue
        if isinstance(value, str):
            found.append(Input(name, help=value))
            continue
        if not isinstance(value, Mapping):
            problems.append(f"入力 {name} は説明の文字列か表（help・required・default）です。")
            continue
        unknown = sorted(set(value) - {"help", "required", "default"})
        if unknown:
            problems.append(f"入力 {name} に知らない項目があります：{', '.join(unknown)}")
        if not isinstance(value.get("help", ""), str) or not isinstance(value.get("required", False), bool):
            problems.append(f"入力 {name} の help は文字列、required は真偽です。")
            continue
        found.append(Input(name, value.get("help", ""), value.get("required", False), value.get("default")))
    return found


def _step(raw, number: int, seen: set[str], kinds: Mapping | None, problems: list[str]) -> Step | None:
    if not isinstance(raw, Mapping):
        problems.append(f"{number} 番目の工程は表です。")
        return None
    step_id = raw.get("id")
    where = f"工程 {step_id}" if isinstance(step_id, str) and step_id else f"{number} 番目の工程"
    if not isinstance(step_id, str) or not _ID.match(step_id):
        problems.append(f"{where} の id は英数字・_・- で書きます。")
        return None
    if step_id in seen:
        problems.append(f"工程 {step_id} が重なっています（id は1つずつ）。")
        return None
    kind_name = raw.get("type")
    if not isinstance(kind_name, str) or not kind_name:
        problems.append(f"{where} に type がありません。")
        return None
    settings = {key: value for key, value in raw.items() if key not in COMMON_KEYS}
    if kinds is not None:
        if kind_name not in kinds:
            problems.append(f"{where} の type「{kind_name}」はありません（使えるもの：{', '.join(sorted(kinds))}）。")
        else:
            kind = as_kind(kinds[kind_name])
            if kind.settings is not None:
                unknown = sorted(set(settings) - set(kind.settings))
                if unknown:
                    problems.append(f"{where} に知らない項目があります：{', '.join(unknown)}")
            missing = [key for key in kind.required if key not in settings]
            if missing:
                problems.append(f"{where}（{kind_name}）に {', '.join(missing)} がありません。")
            if kind.check is not None and not missing:
                problems += [f"{where}：{text}" for text in kind.check(settings)]
    conditions = {}
    for key in ("when", "pass_if"):
        value = raw.get(key, "")
        if not isinstance(value, str):
            problems.append(f"{where} の {key} は文字列です。")
            value = ""
        if value:
            _check_condition(value, f"{where} の {key}", problems)
        conditions[key] = value
    retries = raw.get("retries", 0)
    if not isinstance(retries, int) or isinstance(retries, bool) or not 0 <= retries <= MAX_RETRIES:
        problems.append(f"{where} の retries は 0〜{MAX_RETRIES} の整数です。")
        retries = 0
    timeout = raw.get("timeout")
    if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0):
        problems.append(f"{where} の timeout は正の数（秒）です。")
        timeout = None
    on_fail = _back(raw.get("on_fail"), f"{where} の on_fail", ("to", "max", "message"), problems)
    loop = _back(raw.get("loop"), f"{where} の loop", ("to", "max", "until"), problems)
    return Step(step_id, kind_name, conditions["when"], conditions["pass_if"], on_fail, loop, retries,
                float(timeout) if timeout is not None else None, settings)


def _back(raw, where: str, keys: tuple[str, ...], problems: list[str]) -> Back | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        problems.append(f"{where} は表です（例：{{ to = \"impl\", max = 3 }}）。")
        return None
    unknown = sorted(set(raw) - set(keys))
    if unknown:
        problems.append(f"{where} に知らない項目があります：{', '.join(unknown)}")
    to, most = raw.get("to"), raw.get("max", 1)
    if not isinstance(to, str) or not to:
        problems.append(f"{where} に to（戻る工程）がありません。")
        return None
    if not isinstance(most, int) or isinstance(most, bool) or not 1 <= most <= MAX_BACKS:
        problems.append(f"{where} の max は 1〜{MAX_BACKS} の整数です。")
        return None
    message, until = raw.get("message", ""), raw.get("until", "")
    if not isinstance(message, str) or not isinstance(until, str):
        problems.append(f"{where} の message・until は文字列です。")
        return None
    if until:
        _check_condition(until, f"{where} の until", problems)
    return Back(to, most, message, until)


def _check_condition(text: str, where: str, problems: list[str]) -> None:
    try:
        _expand.condition(text)
    except ValueError as error:
        problems.append(f"{where}：{error}")


def _check_references(step: Step, ids: list[str], problems: list[str]) -> None:
    """`${…}` の名前：知らない頭（inputs・vars・steps・out・run 以外）と、定義にない steps.<id> を誤りに。"""
    texts = [step.when, step.pass_if, *_expand.strings(step.settings)]
    texts += [step.on_fail.message] if step.on_fail else []
    texts += [step.loop.until] if step.loop else []
    for text in texts:
        for name in _expand.references(text):
            parts = name.split(".")
            if parts[0] not in _expand.ROOTS:
                problems.append(f"工程 {step.id} の「${{{name}}}」：頭は {'・'.join(_expand.ROOTS)} のどれかです。")
            elif parts[0] == "steps" and (len(parts) < 2 or parts[1] not in ids):
                problems.append(f"工程 {step.id} の「${{{name}}}」：工程 {parts[1] if len(parts) > 1 else ''} は定義にありません。")
