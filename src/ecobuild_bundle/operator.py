"""オペレーター：ECOBuild の操作係のエージェント（このPCに1つ）。コードは書かず、頼まれた操作を ECOBuild のコマンドで行う。

作業ディレクトリは ECOBUILD_HOME/agents/operator。指示・許可・フックの一式（ecoagent.kit）は使う側（CLI）が
中身を決めて prepare で置く（起動のたびに作り直す）。許すのは ECOBuild のコマンドと読むだけのコマンドで、ファイルの編集は禁止。
使い方は2つ：start（新しい画面で会話する）、ask（画面を開かず1回話しかける。会話の窓のあるアプリ向け）。
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import ecoagent
from ecobuild import settings as _settings
from ecobuild.errors import EcoBuildError, ErrorCode

FOLDER = Path("agents") / "operator"
READ, CHANGE, CONFIRM, HUMAN = ecoagent.guard.READ, ecoagent.guard.CHANGE, ecoagent.guard.CONFIRM, ecoagent.guard.HUMAN


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


def prepare(instructions: str, *, program: str, guard: str) -> OperatorKit:
    """一式を置く。program：許すコマンドの名前（ecobuild）。guard：シェルのコマンドの前に実行するフック。"""
    allow = tuple(f"{tool}({program}:*)" for tool in ("Bash", "PowerShell"))
    kit = ecoagent.kit.prepare(directory(), instructions, allow=allow, guard=guard)
    return OperatorKit(kit.directory, kit.instructions, kit.settings)


def start(command: tuple[str, ...] = ecoagent.DEFAULT_COMMAND) -> OperatorStarted:
    with _agent_error():
        session = ecoagent.start(directory(), command)
    return OperatorStarted(session.pid, session.command, session.directory)


def ask(text: str, *, session: str | None = None,
        command: tuple[str, ...] = ecoagent.DEFAULT_COMMAND) -> OperatorReply:
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
        raise EcoBuildError(ErrorCode.AGENT_ERROR, error.message, hint=error.hint, details=error.code) from error
