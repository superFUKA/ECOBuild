"""CIのワークフロー（GitHub Actions）の共通部品。型の ci_workflow が使う。

トリガー（on:）・ランナー・構成など、型によらない部分はここで作る。型はビルドの手順と型に固有のmatrixを書く。
値はYAMLとして正しく書く（そのまま書けない値は引用符で囲む）。
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

from .config import CI_RUNNERS, CiSettings, ModuleConfig

_PLAIN = re.compile(r"[A-Za-z][A-Za-z0-9._/-]*")
_RESERVED = {"true", "false", "yes", "no", "on", "off", "y", "n", "null"}  # 引用符がないと文字列にならない


def yaml_text(value: str) -> str:
    """YAMLの文字列。英字で始まる名前（main・release/1.0・windows-latest 等）はそのまま、それ以外
    （** や ! で始まるブランチのパターン、空白・: を含むコマンド等）は引用符で囲む。"""
    if _PLAIN.fullmatch(value) and value.lower() not in _RESERVED:
        return value
    return json.dumps(value, ensure_ascii=False)


def yaml_list(values: Iterable[str]) -> str:
    return "[" + ", ".join(yaml_text(value) for value in values) + "]"


def trigger(config: ModuleConfig) -> list[str]:
    """on: の部分。pushは [ci] の branches（既定：default_base）で、PRと手動では常に動く。"""
    return ["on:", "  push:", f"    branches: {yaml_list(config.ci.branches or (config.default_base,))}",
            "  pull_request:", "  workflow_dispatch:      # ecobuild ci run（手動での実行）"]


def runners(ci: CiSettings, default_os: tuple[str, ...]) -> str:
    """matrix の os（[ci] の os、なければ型の既定のOS）。"""
    return yaml_list(CI_RUNNERS[name] for name in (ci.os or default_os))
