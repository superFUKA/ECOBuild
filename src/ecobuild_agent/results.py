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
    """ecobuild agent registry show・add・set・remove：1つの登録と、その文書（agent.md の中身）・最初の発言（GUI の編集）。"""
    document: str = ""
    first_prompt: str = ""


@dataclass(frozen=True)
class AgentRoleRules:
    """ecobuild agent rules：1つの登録へのモジュールの決まり。tools：登録（このPC）で渡すツール。"""
    name: str
    title: str
    text: str                       # その登録のエージェントだけへの文
    deny: tuple[str, ...]           # その登録に使わせないツール（fnmatch）
    tools: tuple[str, ...]


@dataclass(frozen=True)
class AgentTool:
    """エージェントに渡せるツール。mark：read・change・owner（コマンドのツール）・children（子を扱うツール）。"""
    name: str
    mark: str
    summary: str


@dataclass(frozen=True)
class AgentRules:
    """ecobuild agent rules show・set：モジュールのエージェント向けの決まり（作業ツリーにあるもの）。
    in_force：起動したエージェントに効く版（作成元のブランチ。読めなければ空）。pending：作業ツリーのものが、まだ効く版と違う。"""
    root: Path
    in_force: str
    pending: bool
    common: str
    roles: tuple                    # AgentRoleRules（登録の名前の順。登録にない名前の文・ツールも）
    tools: tuple = ()               # AgentTool（show で --tools のとき）
    changed: tuple[str, ...] = ()   # set で書いた・消したファイル
    committed: str = ""             # set でコミットした版（しなければ空）


def registration_view(registration, *, document: bool = False) -> AgentRegistrationView:
    """ecobuild_agent.registry.Registration を CLI の結果に（document：文書の中身も入れる）。"""
    from . import registry
    fields = dict(name=registration.name, title=registration.title, source=registration.source,
                  human_start=registration.human_start, model=registration.model, children=registration.children,
                  max_children=registration.max_children, tools=registration.tools,
                  document_path=registry.document_path(registration))
    if document:
        return AgentRegistrationShown(**fields, document=registration.document, first_prompt=registration.first_prompt)
    return AgentRegistrationView(**fields)
