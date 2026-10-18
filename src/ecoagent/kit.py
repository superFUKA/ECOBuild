"""エージェントの一式：決まった場所に、指示（CLAUDE.md）と許可・フックの設定（.claude/settings.json）を置く。

作業をしないエージェント（操作係など）を、決まった道具だけで動かすためのもの。中身（指示の文・許すコマンド・フック）は使う側が決める。
置き場所はエージェントの作業ディレクトリになる。起動は start（画面）・ask（1回の発言）に、その場所を渡す。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

INSTRUCTIONS = "CLAUDE.md"
SETTINGS = Path(".claude") / "settings.json"
EDIT_TOOLS = ("Edit", "Write", "NotebookEdit")
SHELL_TOOLS = "Bash|PowerShell"


@dataclass(frozen=True)
class Kit:
    directory: Path
    instructions: Path
    settings: Path


def prepare(directory: Path | str, instructions: str, *, allow: tuple[str, ...] = (),
            deny: tuple[str, ...] = EDIT_TOOLS, guard: str | None = None) -> Kit:
    """directory に一式を書く（毎回作り直す。使う側の版が変わっても古い指示が残らないように）。
    allow・deny：許可の規則（"Bash(ecobuild:*)" 等）。guard：シェルのコマンドの前に実行するフックのコマンド。"""
    directory = Path(directory)
    (directory / SETTINGS).parent.mkdir(parents=True, exist_ok=True)
    settings: dict = {"permissions": {"allow": list(allow), "deny": list(deny)}}
    if guard:
        settings["hooks"] = {"PreToolUse": [{"matcher": SHELL_TOOLS, "hooks": [{"type": "command", "command": guard}]}]}
    _write(directory / INSTRUCTIONS, instructions if instructions.endswith("\n") else instructions + "\n")
    _write(directory / SETTINGS, json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
    return Kit(directory, directory / INSTRUCTIONS, directory / SETTINGS)


def _write(path: Path, text: str) -> None:
    if not path.is_file() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8", newline="\n")
