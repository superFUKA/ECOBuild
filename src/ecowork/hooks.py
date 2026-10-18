"""gitのフック：タスクブランチ（task/<番号>-<名前>）でないブランチへの直接のコミット・pushを、git自体に止めさせる。
コミットのメッセージからは、AIの署名を消す（commit-msg）。

ecowork（ECOBuild）の外でgitを直接使っても、作業の流れから外れられないようにする（ルールではなく仕組みで）。
ecowork自身のgitの呼び出しは、環境変数 ECOWORK_ALLOW で通す（モジュールの作成の初回コミット等）。
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

MARKER = "# ecowork-guard"
ALLOW = "ECOWORK_ALLOW"

PRE_COMMIT = f"""#!/bin/sh
{MARKER}：タスクブランチ（task/<番号>）でないブランチへの直接のコミットを止める。
[ -n "${ALLOW}" ] && exit 0
branch=$(git symbolic-ref --short -q HEAD)
case "$branch" in
  task/*) exit 0 ;;
esac
echo "ECOBuild: ${{branch:-（切り離された状態）}} へは直接コミットできません。" >&2
echo "  作業はタスクブランチで行います：ecobuild task start <Issue番号>" >&2
exit 1
"""

PRE_PUSH = f"""#!/bin/sh
{MARKER}：タスクブランチ（task/<番号>）でないブランチへの直接のpush（削除を含む）を止める。
[ -n "${ALLOW}" ] && exit 0
status=0
while read -r local_ref local_sha remote_ref remote_sha; do
  case "$remote_ref" in
    refs/heads/task/*) ;;
    refs/heads/*)
      echo "ECOBuild: ${{remote_ref#refs/heads/}} へは直接pushできません。変更はPRのマージで入れます（ecobuild task submit）。" >&2
      status=1 ;;
  esac
done
exit $status
"""

# AIの署名（「Co-Authored-By: Claude …」「Generated with Claude Code」等）はコミットに残さない。
# 作業した者はコミットの作者で分かる（AIはAI用のアカウントで動く）。人の Co-Authored-By は残す。
# ECOWORK_ALLOW でも通さない（ecowork 自身のコミットにも当てはめる）。sed の方言を避けて awk で書く。
# LC_ALL=C：tolower を ASCII だけにし、日本語・絵文字のバイトで awk が乱れないように。
AI_NAMES = "claude|anthropic|copilot|openai|chatgpt|codex|cursor|gemini|devin|aider|windsurf|codeium"

COMMIT_MSG = f"""#!/bin/sh
{MARKER}：AIの署名（Co-Authored-By・Generated with …）をコミットのメッセージから消す。
file="$1"
LC_ALL=C awk '
{{ line = tolower($0) }}
line ~ /^[ \\t]*co-authored-by:/ && line ~ /({AI_NAMES})/ {{ next }}
line ~ /generated (with|by) \\[?({AI_NAMES})/ {{ next }}
/^[ \\t]*$/ {{ blank = blank $0 "\\n"; next }}
{{ printf "%s", blank; blank = ""; print }}
' "$file" > "$file.ecowork" && mv "$file.ecowork" "$file"
"""

HOOKS = {"pre-commit": PRE_COMMIT, "commit-msg": COMMIT_MSG, "pre-push": PRE_PUSH}


def install(hooks_directory: Path) -> tuple[str, ...]:
    """フックを入れる（既にあれば内容を最新に）。ecowork のものでないフックがあれば触らない。入れた名前を返す。"""
    hooks_directory.mkdir(parents=True, exist_ok=True)
    installed = []
    for name, text in HOOKS.items():
        path = hooks_directory / name
        if path.exists():
            current = path.read_text(encoding="utf-8", errors="replace")
            if MARKER not in current:
                continue  # 利用者のフック
            if current == text:
                continue
        path.write_text(text, encoding="utf-8", newline="\n")
        if os.name != "nt":
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        installed.append(name)
    return tuple(installed)


def installed(hooks_directory: Path) -> bool:
    """ecowork のフックがすべて入っているか。"""
    paths = [hooks_directory / name for name in HOOKS]
    return all(p.exists() and MARKER in p.read_text(encoding="utf-8", errors="replace") for p in paths)
