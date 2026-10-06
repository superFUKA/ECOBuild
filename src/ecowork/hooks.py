"""gitのフック：作業空間（task/<番号>）でないブランチへの直接のコミット・pushを、git自体に止めさせる。

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
{MARKER}：作業空間（task/<番号>）でないブランチへの直接のコミットを止める。
[ -n "${ALLOW}" ] && exit 0
branch=$(git symbolic-ref --short -q HEAD)
case "$branch" in
  task/*) exit 0 ;;
esac
echo "ECOBuild: ${{branch:-（切り離された状態）}} へは直接コミットできません。" >&2
echo "  作業は作業空間で行います：ecobuild task start <Issue番号>" >&2
exit 1
"""

PRE_PUSH = f"""#!/bin/sh
{MARKER}：作業空間（task/<番号>）でないブランチへの直接のpush（削除を含む）を止める。
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

HOOKS = {"pre-commit": PRE_COMMIT, "pre-push": PRE_PUSH}


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
