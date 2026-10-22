"""エージェントの拡張の戻り値。CLIはこれを人向けの表示とJSONへ変換する。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentConversations:
    """ecobuild agent conversations：作業空間でのエージェント（Claude Code）の会話。新しい順（続きから再開するものを選ぶ）。"""
    directory: Path
    conversations: tuple            # ecoagent.Conversation（id・名前・最後に書かれた日時・ブランチ・発言の数）
    note: str = ""                  # 一覧を読めなかったわけ（コンテナが止まっている等）



@dataclass(frozen=True)
class AgentRegistrationView:
    """ecobuild agent registry list：1つの登録。"""
    name: str
    title: str
    source: str                     # sample（ECOBuild が配る見本）・user（ユーザーの登録）
    human_start: bool
    model: str                      # 空なら Claude Code の既定
    children: tuple[str, ...]       # 起動してよい登録の名前
    max_children: int
    tools: tuple[str, ...]          # 渡すツールの名前の fnmatch の並び
    document_path: Path


@dataclass(frozen=True)
class AgentRegistrationShown(AgentRegistrationView):
    """ecobuild agent registry show・add・set・remove：1つの登録と、その文書（agent.md の中身）。"""
    document: str = ""


def registration_view(registration, *, document: bool = False) -> AgentRegistrationView:
    """ecobuild_agent.registry.Registration を CLI の結果に（document：文書の中身も入れる）。"""
    from . import registry
    fields = dict(name=registration.name, title=registration.title, source=registration.source,
                  human_start=registration.human_start, model=registration.model, children=registration.children,
                  max_children=registration.max_children, tools=registration.tools,
                  document_path=registry.document_path(registration))
    if document:
        return AgentRegistrationShown(**fields, document=registration.document)
    return AgentRegistrationView(**fields)
