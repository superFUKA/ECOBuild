"""オペレーター：ECOBuild の操作係のエージェント（このPCに1つ）。コードは書かず、頼まれた操作を ECOBuild のコマンドで行う。

作業ディレクトリは ECOBUILD_HOME/agents/operator。指示・許可・フックの一式（ecoagent.kit）は使う側（CLI）が
中身を決めて prepare で置く（起動のたびに作り直す）。許すのは ECOBuild のコマンドと読むだけのコマンドで、ファイルの編集は禁止。
使い方は2つ：start（新しい画面で会話する）、ask（画面を開かず1回話しかける。会話の窓のあるアプリ向け）。
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import ecoagent
from ecobuild import settings as _settings

from . import status as agent_status
from .errors import from_ecoagent

FOLDER = Path("agents") / "operator"
READ, CHANGE, CONFIRM, HUMAN = ecoagent.guard.READ, ecoagent.guard.CHANGE, ecoagent.guard.CONFIRM, ecoagent.guard.HUMAN
REQUESTED = ecoagent.guard.REQUESTED


@dataclass(frozen=True)
class OperatorKit:
    """ecobuild agent operator --prepare：置いた一式（directory で起動すれば、その指示・許可で動く）。"""
    directory: Path
    instructions: Path
    settings: Path


@dataclass(frozen=True)
class OperatorStarted:
    pid: int
    command: tuple[str, ...]
    directory: Path


@dataclass(frozen=True)
class OperatorAction:
    tool: str
    command: str
    ok: bool | None
    output: str


@dataclass(frozen=True)
class OperatorReply:
    """ecobuild agent ask：オペレーターの返答。session を次の ask に渡すと会話が続く。"""
    session: str | None
    text: str
    ok: bool
    actions: tuple[OperatorAction, ...]


def directory() -> Path:
    return _settings.home() / FOLDER


EFFECTS = "effects.json"   # 一式の中：拡張が名乗った操作の重さ（フックが読む）


def prepare(instructions: str, *, program: str, guard: str, effects: dict[str, str] | None = None,
            context: str | None = None) -> OperatorKit:
    """一式を置く。program：許すコマンドの名前（ecobuild）。guard：シェルのコマンドの前に実行するフック。
    effects：拡張の操作の重さ（"<拡張> <操作>" → 重さ）。context：話しかけられるたびに今の状況を渡すフック。"""
    import json
    allow = tuple(f"{tool}({program}:*)" for tool in ("Bash", "PowerShell"))
    kit = ecoagent.kit.prepare(directory(), instructions, allow=allow, guard=guard, context=context)
    (kit.directory / EFFECTS).write_text(json.dumps(effects or {}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return OperatorKit(kit.directory, kit.instructions, kit.settings)


def effects() -> dict[str, str]:
    """一式に置いた拡張の操作の重さ（なければ空）。"""
    import json
    try:
        found = json.loads((directory() / EFFECTS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in found.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(found, dict) else {}


def quick(command: tuple[str, ...]) -> tuple[str, ...]:
    """オペレーターは短い操作が主なので、Claude Code なら考える量を少なく（--effort low。指定があればそのまま）。"""
    command = tuple(command)
    if command[:1] == ("claude",) and "--effort" not in command:
        command = (*command, "--effort", "low")
    return command


def start(command: tuple[str, ...] = ecoagent.DEFAULT_COMMAND) -> OperatorStarted:
    command = quick(command)
    with _agent_error():
        session = ecoagent.start(directory(), command)
    return OperatorStarted(session.pid, session.command, session.directory)


def run(command: tuple[str, ...] = ecoagent.DEFAULT_COMMAND) -> int:
    """この端末で動かして待つ（画面を持つ別のアプリが、自分の端末の中で常駐させるとき）。Claude Code なら、一式の
    許可・フックと、状態の書き出し（agent_status：返答の終わり・モデル）を1つの --settings で渡す（フォルダーの
    信頼を待たずに効く）。"""
    import json
    command = quick(command)
    if command[:1] == ("claude",):
        # 起動ごとに別の置き場所（同じPCでオペレーターが2つ動いても、互いの状態を消さない）。古いものは片付ける
        agent_status.forget_old("operator-")
        folder = agent_status.prepare(f"operator-{os.getpid()}")
        agent_status.announce(folder)
        try:
            base = json.loads((directory() / ecoagent.kit.SETTINGS).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            base = {}
        command = (*command, "--settings", agent_status.settings_argument(folder, folder.as_posix(), agent_status.host_python(), base))
    with _agent_error():
        return ecoagent.run(directory(), command)


def ask(text: str, *, session: str | None = None,
        command: tuple[str, ...] = ecoagent.DEFAULT_COMMAND) -> OperatorReply:
    command = quick(command)
    with _agent_error():
        reply = ecoagent.ask(directory(), text, session=session, command=command,
                             settings=directory() / ecoagent.kit.SETTINGS)
    return OperatorReply(reply.session, reply.text, reply.ok,
                         tuple(OperatorAction(a.tool, a.command, a.ok, a.output) for a in reply.actions))


def guard(data: str, classify: Callable[[list[str]], tuple[str, str]], *, program: str) -> tuple[int, str]:
    """オペレーターのフック：シェルのコマンド（フックの入力の JSON）を調べる。(終了コード, エージェントに伝える文)。
    classify：program の引数 → (重さ, コマンドの名前)。"""
    policy = ecoagent.guard.Policy(
        frozenset({program}), classify, role="オペレーター",
        refusals={HUMAN: f"これは人が行う操作です（{program} の準備・更新・秘密の値の入力・オペレーター自身の操作など）。"
                         "ユーザーに、自分で実行するよう伝えてください。"})
    return ecoagent.guard.hook(data, policy)


@contextmanager
def _agent_error():
    try:
        yield
    except ecoagent.AgentError as error:
        raise from_ecoagent(error) from error
