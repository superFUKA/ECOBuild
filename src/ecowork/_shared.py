"""ecowork の Repository とその一部（_tasks.py 等）が共有する定数と関数。"""

from __future__ import annotations

import functools
import re
from pathlib import Path

_REVIEW_KEY = "ecowork.review"              # task review で確認中のPR（手元だけ）
_REVIEW_RETURN_KEY = "ecowork.review-return"
_STASH_BRANCH = re.compile(r"^(?:WIP on|On) ([^:]+):")


def _stash_branch(message: str) -> str | None:
    """退避した変更のメッセージ（git stash list の %gs）から、退避したブランチ。"""
    match = _STASH_BRANCH.match(message)
    return None if match is None or match.group(1) == "(no branch)" else match.group(1)


def reusing_reads(operation):
    """Repository の操作の間、GitHub の同じ読みを1回にする（ecotask.github の reusing_reads）。"""
    @functools.wraps(operation)
    def run(self, *args, **kwargs):
        with self.github.reusing_reads():
            return operation(self, *args, **kwargs)
    return run


_PR_IN_SUBJECT = re.compile(r"\(#(\d+)\)\s*$")


_MARKER_LINE = re.compile(r"^(?:<{7}|>{7}|\|{7})(?: |$)|^={7}$")


def _markers_in(path: Path, name: str) -> list[str]:
    """ファイルに残っている衝突の印の場所（「パス:行」）。読めない・ないファイルは空。"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [f"{name}:{number}" for number, line in enumerate(text.splitlines(), 1) if _MARKER_LINE.match(line)]


def _github_name(url: str) -> str | None:
    """origin の URL が GitHub のものなら、その 所有者/名前（URLに書かれた形のまま）。"""
    match = re.search(r"github\.com[:/]+([^/]+/[^/]+?)(?:\.git)?/?$", url)
    return match.group(1) if match else None
