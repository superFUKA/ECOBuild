"""エージェントの拡張の戻り値。CLIはこれを人向けの表示とJSONへ変換する。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentStarted:
    """ecobuild agent start：起動したエージェント（新しい画面で動いている）。"""
    pid: int
    command: tuple[str, ...]
    directory: Path


@dataclass(frozen=True)
class AgentConversations:
    """ecobuild agent conversations：作業空間でのエージェント（Claude Code）の会話。新しい順（続きから再開するものを選ぶ）。"""
    directory: Path
    conversations: tuple            # ecoagent.Conversation（id・名前・最後に書かれた日時・ブランチ・発言の数）
    note: str = ""                  # 一覧を読めなかったわけ（コンテナが止まっている等）
