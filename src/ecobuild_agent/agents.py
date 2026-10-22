"""エージェントの記録：起動したエージェント1人ごとの ID・登録・親・持ち主か手伝いか・タスク・作業空間・会話。

1つの作業空間に、タスクの持ち主と手伝いが何人もいる。状態の置き場所（status）はエージェントごとに分け
（ECOBUILD_HOME/agents/status/<コンテナの名前>/<ID>/）、その中の agent.json に記録を持つ。
- ID は a-<16進の10文字>。表示名は別に持つ（登録の名前か、子なら <登録名>-<連番>）。
- 親子は記録で持つ（作業空間は入れ子にしない）。直接の子は「親 = 自分」の記録。
- 続きからの起動は、会話の ID（session）で記録を引く。
前の版の記録（作業空間の中の member.json・roles.json、置き場所の直下のファイル）は読まない。
"""

from __future__ import annotations

import os
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from ecobuild.errors import EcoBuildError

from . import status
from .errors import ErrorCode

RECORD = "agent.json"     # 状態の置き場所の中：エージェントの記録
ID_PREFIX = "a-"
OWNER, HELPER = "owner", "helper"   # タスクの持ち主・手伝い（親の作業空間を一緒に使い、コミット・提出しない）
KINDS = (OWNER, HELPER)


@dataclass(frozen=True)
class AgentRecord:
    """エージェント1人の記録。task：{"number", "branch"}（手伝いは親のタスク）。workspace：作業空間（このPCの場所）。
    session：今の会話の ID（続きから起動するときに引く）。owner_session：起動を頼んだ会話（人が起動したものは空）。"""
    id: str
    name: str
    registration: str
    parent: str | None
    kind: str
    task: dict | None
    workspace: str
    model: str = ""
    session: str = ""
    owner_session: str = ""
    report_only: bool = False
    started_at: float = 0.0

    @property
    def folder(self) -> Path:
        """状態の置き場所（受け箱・会話の様子・guide.md・mcp.json）。"""
        return status.directory(self.id) or status.create_directory(Path(self.workspace), self.id)

    @property
    def root(self) -> Path:
        return Path(self.workspace)


def new_id() -> str:
    return ID_PREFIX + uuid.uuid4().hex[:10]


def is_id(text: str) -> bool:
    return isinstance(text, str) and text.startswith(ID_PREFIX) and len(text) == len(ID_PREFIX) + 10 \
        and all(c in "0123456789abcdef" for c in text[len(ID_PREFIX):])


def create(*, registration: str, workspace: Path, kind: str = OWNER, parent: str | None = None,
           task: dict | None = None, name: str = "", model: str = "", session: str = "", owner_session: str = "",
           report_only: bool = False) -> AgentRecord:
    """新しいエージェントの記録を作り、置き場所に書く。name を省けば、登録の名前（子なら <登録名>-<連番>）。"""
    if kind not in KINDS:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"エージェントの種類 {kind!r} はありません。",
                            hint="owner（タスクの持ち主）か helper（手伝い）です。")
    agent_id = new_id()
    if not name:
        name = registration
        if parent:
            used = {child.name for child in children(parent)}
            number = 1 + sum(1 for child in children(parent) if child.registration == registration)
            while f"{registration}-{number}" in used:
                number += 1
            name = f"{registration}-{number}"
    record = AgentRecord(agent_id, name, registration, parent or None, kind,
                         dict(task) if task else None, str(Path(workspace)), model, session, owner_session,
                         report_only, time.time())
    folder = status.create_directory(Path(workspace), agent_id)
    _save(folder, record)
    return record


def load(agent_id: str) -> AgentRecord:
    """ID のエージェントの記録（なければ誤り）。"""
    folder = status.directory(agent_id) if is_id(agent_id) else None
    found = _read(folder) if folder is not None else None
    if found is None:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"エージェント {agent_id} はありません。",
                            hint="エージェントの ID は agent status で見られます（a- で始まります）。")
    return found


def update(agent_id: str, **changes) -> AgentRecord:
    """記録の項目を変えて書き直す（session 等）。"""
    record = replace(load(agent_id), **changes)
    _save(status.directory(agent_id), record)
    return record


def all_records() -> list[AgentRecord]:
    """このPCのエージェントの記録すべて（起動した順）。"""
    found = [record for folder in status.folders() if (record := _read(folder)) is not None]
    return sorted(found, key=lambda r: (r.started_at, r.id))


def children(agent_id: str) -> list[AgentRecord]:
    """直接の子（親 = agent_id）。"""
    return [record for record in all_records() if record.parent == agent_id]


def by_session(session: str) -> AgentRecord | None:
    """会話 session のエージェント（続きから起動するとき）。"""
    if not session:
        return None
    return next((record for record in reversed(all_records()) if record.session == session), None)


def in_workspace(root: Path) -> list[AgentRecord]:
    """作業空間 root のエージェント（持ち主・手伝い）。"""
    key = _key(root)
    return [record for record in all_records() if _key(record.workspace) == key]


def forget(agent_id: str) -> None:
    """記録と置き場所を消す（閉じた子・片付け）。"""
    folder = status.directory(agent_id) if is_id(agent_id) else None
    if folder is not None:
        shutil.rmtree(folder, ignore_errors=True)


def to_data(record: AgentRecord) -> dict:
    return asdict(record)


def _key(path) -> str:
    try:
        return os.path.normcase(str(Path(path).resolve()))
    except OSError:
        return os.path.normcase(str(Path(path)))


def _save(folder: Path, record: AgentRecord) -> None:
    status._write(folder / RECORD, asdict(record))


def _read(folder: Path) -> AgentRecord | None:
    data = status.read(Path(folder) / RECORD)
    if not isinstance(data, dict) or not is_id(str(data.get("id") or "")):
        return None
    try:
        task = data.get("task") if isinstance(data.get("task"), dict) else None
        return AgentRecord(str(data["id"]), str(data.get("name") or data["id"]), str(data.get("registration") or ""),
                           str(data["parent"]) if data.get("parent") else None,
                           str(data.get("kind") or OWNER), task, str(data.get("workspace") or ""),
                           str(data.get("model") or ""), str(data.get("session") or ""),
                           str(data.get("owner_session") or ""), bool(data.get("report_only")),
                           float(data.get("started_at") or 0))
    except (TypeError, ValueError):
        return None


__all__ = ["AgentRecord", "HELPER", "KINDS", "OWNER", "RECORD", "all_records", "by_session", "children", "create",
           "forget", "in_workspace", "is_id", "load", "new_id", "to_data", "update"]
