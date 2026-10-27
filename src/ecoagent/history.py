"""これまでの会話の一覧（Claude Code が記録した会話。claude --resume <id> で続きから再開できる）。

Claude Code は、会話を設定の場所（CLAUDE_CONFIG_DIR。なければ ~/.claude）の projects/<場所の名前>/<id>.jsonl に記録する。
場所の名前は、作業ディレクトリの英数字以外を - にしたもの。会話の名前は、/rename で付けたもの、なければ Claude が
付けたもの、なければ最初の発言。

標準のライブラリだけを使う（このファイルだけを別の Python で動かせる：python3 history.py <場所> [ブランチ]。
コンテナの中の会話を、中の Python で読むため。結果は JSON）。
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

TITLE_LENGTH = 80        # 最初の発言を名前にするときの長さ
NAME_LENGTH = 200        # 場所の名前がこれより長いと、Claude Code は切り詰めて後ろにハッシュを付ける
UNKNOWN_BRANCH = "HEAD"    # ブランチを読めなかった（取り出していない等）ときに Claude Code が記録するもの


@dataclass(frozen=True)
class Conversation:
    id: str
    title: str
    updated: str          # 最後に書かれた日時（ISO 8601・UTC。コンテナの中で読んでも同じ）
    branch: str           # 最後の発言のときの git のブランチ（分からなければ空）
    prompts: int          # 人の発言の数


def conversations(directory: Path | str, *, config_dir: Path | str | None = None, branch: str | None = None,
                  limit: int = 20) -> list[Conversation]:
    """directory での会話を新しい順に limit 件まで。branch：そのブランチでの会話だけ（同じ場所を別の作業で使うとき。
    コンテナの中の /work 等）。ブランチの分からない会話（記録が空・HEAD）は、どのブランチにも入れる。
    発言のない会話（開いてすぐ閉じた）は入れない。"""
    folder = _folder(Path(config_dir or os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects",
                     str(directory))
    if folder is None:
        return []
    try:
        files = sorted(folder.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    except OSError:
        return []
    found = []
    for file in files:
        if len(found) >= limit:
            break
        try:
            conversation = _read(file)
        except OSError:
            continue
        if conversation and (not branch or conversation.branch in (branch, "", UNKNOWN_BRANCH)):
            found.append(conversation)
    return found


def _folder(projects: Path, directory: str) -> Path | None:
    name = re.sub(r"[^A-Za-z0-9]", "-", directory)
    if (projects / name).is_dir():
        return projects / name
    try:   # ドライブ文字の大小等の違い（Windows）・長い場所（切り詰めて後ろにハッシュ）
        for candidate in projects.iterdir():
            other = candidate.name.lower()
            if other == name.lower() or (len(name) > NAME_LENGTH and other.startswith(name[:NAME_LENGTH].lower())):
                return candidate
    except OSError:
        pass
    return None


def _read(file: Path) -> Conversation | None:
    custom = ai = first = branch = ""
    prompts = 0
    with file.open(encoding="utf-8", errors="replace") as lines:
        for line in lines:
            # 大きな記録は道具の結果が主なので、要る行だけを JSON として読む
            if '"custom-title"' in line or '"ai-title"' in line:
                record = _json(line)
                custom = record.get("customTitle") or custom
                ai = record.get("aiTitle") or ai
            elif '"user"' in line:
                record = _json(line)
                if record.get("type") != "user" or record.get("isMeta") or record.get("isSidechain"):
                    continue
                branch = record.get("gitBranch") or branch
                text = _text(record.get("message", {}).get("content"))
                if text:
                    prompts += 1
                    first = first or text
    if not prompts:
        return None
    title = custom or ai or " ".join(first.split())[:TITLE_LENGTH]
    updated = datetime.datetime.fromtimestamp(file.stat().st_mtime, datetime.timezone.utc).isoformat(timespec="seconds")
    return Conversation(file.stem, title, updated, branch, prompts)


def _json(line: str) -> dict:
    try:
        record = json.loads(line)
    except ValueError:
        return {}
    return record if isinstance(record, dict) else {}


def _text(content) -> str:
    """人の発言の文（道具の結果・コマンドの印 <command-name> 等は発言にしない）。"""
    if isinstance(content, list):
        content = "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    if not isinstance(content, str) or content.lstrip().startswith("<"):
        return ""
    return content.strip()


if __name__ == "__main__":
    found = conversations(sys.argv[1], branch=sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None,
                          limit=int(sys.argv[3]) if len(sys.argv) > 3 else 20)
    print(json.dumps([asdict(c) for c in found], ensure_ascii=False))
