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
    running: tuple = ()             # 今動いているエージェントの会話（{session, agent, name}。続きからは起動できない：2重になる）



@dataclass(frozen=True)
class AgentRegistrationView:
    """ecobuild agent registry list・agent preset list：1つの登録。"""
    name: str
    title: str
    source: str                     # sample（ECOBuild が配る見本）・preset（このPCのプリセット）・module（モジュールの登録）
    human_start: bool
    model: str                      # 空なら Claude Code の既定
    children: tuple[str, ...]       # 起動してよい登録の名前
    max_children: int
    tools: tuple[str, ...]          # 渡すツールの名前の fnmatch の並び
    folder: str                     # 置き場所（agent.toml・agent.md のあるフォルダー）
    pending: bool = False           # モジュールの登録：作業ツリーのものが、作成元に取り込まれたものと違う（まだ効かない）
    evaluation: str = ""            # 改善のループ：評価のしかた（空なら任された仕事に書かれたもの）
    max_rounds: int = 0             # 評価し直す回数の上限（0 なら決めない）
    max_turns: int = 0              # ターン数の上限（アプリ用の起動。0 ならなし）
    max_cost: float = 0.0           # 費用の上限（ドル。アプリ用の起動。0 ならなし）
    lessons: str = ""               # 教訓の記録先（モジュールの中のフォルダー。空なら報告だけ）
    skills: tuple[str, ...] = ("*",)   # 使えるスキル（モジュールのスキルの名前の fnmatch の並び）


@dataclass(frozen=True)
class AgentRegistrationShown(AgentRegistrationView):
    """ecobuild agent registry show・add・set・remove（preset も）：1つの登録と、その文書（agent.md の中身）・最初の発言。
    committed：モジュールの登録を変えてコミットした版（しなければ空）。"""
    document: str = ""
    first_prompt: str = ""
    committed: str = ""


@dataclass(frozen=True)
class AgentSkillView:
    """ecobuild agent skill list・agent skill preset list：1つのスキル。source：module（モジュールのスキル）・
    preset（このPCのスキル）。files：SKILL.md のほかのファイル。pending：作業ツリーのものが、作成元に取り込まれた
    ものと違う（まだエージェントに渡らない）。used_by：使える登録の名前（モジュールのスキル）。"""
    name: str
    description: str
    source: str
    files: tuple[str, ...]
    folder: str
    pending: bool = False
    used_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentSkillShown(AgentSkillView):
    """ecobuild agent skill show・add・set・remove（preset も）：1つのスキルと本文。committed：コミットした版。"""
    document: str = ""
    committed: str = ""


@dataclass(frozen=True)
class AgentTool:
    """エージェントに渡せるツール。mark：read・change・owner（コマンドのツール）・children（子を扱うツール）。"""
    name: str
    mark: str
    summary: str


@dataclass(frozen=True)
class AgentRules:
    """ecobuild agent rules show・set：全エージェント共通の文（作業ツリーにあるもの）。
    in_force：起動したエージェントに効く版（作成元のブランチ。読めなければ空）。pending：作業ツリーのものが、まだ効く版と違う。"""
    root: Path
    in_force: str
    pending: bool
    common: str
    changed: tuple[str, ...] = ()   # set で書いた・消したファイル
    committed: str = ""             # set でコミットした版（しなければ空）


def registration_view(registration, *, document: bool = False, pending: bool = False,
                      committed: str = "") -> AgentRegistrationView:
    """ecobuild_agent.registry.Registration を CLI の結果に（document：文書の中身も入れる）。"""
    fields = dict(name=registration.name, title=registration.title, source=registration.source,
                  human_start=registration.human_start, model=registration.model, children=registration.children,
                  max_children=registration.max_children, tools=registration.tools, folder=registration.folder,
                  pending=pending, evaluation=registration.evaluation, max_rounds=registration.max_rounds,
                  max_turns=registration.max_turns, max_cost=registration.max_cost, lessons=registration.lessons,
                  skills=registration.skills)
    if document:
        return AgentRegistrationShown(**fields, document=registration.document, first_prompt=registration.first_prompt,
                                      committed=committed)
    return AgentRegistrationView(**fields)


def skill_view(skill, *, document: bool = False, pending: bool = False, used_by: tuple[str, ...] = (),
               committed: str = "") -> AgentSkillView:
    """ecobuild_agent.skills.Skill を CLI の結果に（document：本文も入れる）。"""
    fields = dict(name=skill.name, description=skill.description, source=skill.source, files=skill.files,
                  folder=skill.folder, pending=pending, used_by=used_by)
    if document:
        return AgentSkillShown(**fields, document=skill.document, committed=committed)
    return AgentSkillView(**fields)
