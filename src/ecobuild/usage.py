"""作業空間を使っている最中か（使用中）を確かめる。

作業空間（元の clone の git worktree）はタスクごとに作り、タスクの完了・作業を捨てる等で作業空間ごと消える。そこで、
作業空間を消す操作（task finish・drop・close・prune・workspace close・確認の片付け）と、元の clone・依存先の clone・前の版の
clone でその場で切り替える操作の直前に、中で動いているものがないかを確かめ、あれば止める（ecowork の Hooks.in_use・
branch_in_use。ecobuild.module がつなぐ）。

使用中とみなすもの：
- 実行中のコマンド（COMMANDS：作業空間のファイルを使って長く動くもの）。running で、作業空間の .ecobuild/running.json に
  pid を書く。コンテナの中で動かすものは、渡しているこのPCの CLI が書く（中の pid はこのPCでは確かめられない）。
- 拡張が知っているもの（ecobuild_agent：動いているエージェント）。add_source で口を足す（本体は拡張を知らない。つなぐのは
  ecobuild_bundle）。

以前の版のロック（手動のロック・workspace lock／unlock・.ecobuild/lock.json・コンテナが動いている間のロック）はなくした：
ロックは1つの clone をタスクごとに切り替えて使っていた頃に、使用中の作業空間がほかのタスクに切り替えられないよう守るもの
だった。作業空間がタスクごとになったので、守り続ける必要はなく、消す・切り替える直前に確かめれば足りる。
確かめるのはその直前だけで、status・workspace list では調べない。確かめる口は軽くする（プロセス・ファイルを見るだけにし、
docker・WSL・GitHub を呼ばない）。
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from . import config as _config
from .fsutil import locked, process_alive
from .workspaces import exclude

FILE_NAME = f"{_config.DIRECTORY}/running.json"   # 実行中のコマンド
LOCK_NAME = f"{_config.DIRECTORY}/running.lock"   # running.json を読んで書き直す間の排他

# 実行中は使用中とみなすコマンド（ビルド・テスト・実行・確認〔task submit は中で check を行う〕：作業空間のファイルを使って
# 長く動くので、その間に作業空間が消えたり切り替わったりすると困る。ほかは短いので対象にしない）
COMMANDS = ("build", "clean", "rebuild", "test", "run", "check", "task submit")

# 拡張の口：作業空間の一覧 → それぞれを使っているもの（日本語の文。同じ順）
Source = Callable[[Sequence[Path]], list[list[str]]]
_sources: list[Source] = []


def add_source(source: Source) -> None:
    """使用中かを調べる口を足す（同じものを2回足しても1つ）。"""
    if source not in _sources:
        _sources.append(source)


def _file(root: Path) -> Path:
    return Path(root) / FILE_NAME


def _changing(root: Path):
    exclude(root, f"/{FILE_NAME}", f"/{LOCK_NAME}")
    return locked(Path(root) / LOCK_NAME, timeout=10)


def _read(root: Path) -> list[dict]:
    try:
        data = json.loads(_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    commands = data.get("commands") if isinstance(data, dict) else None
    return [c for c in commands or [] if isinstance(c, dict) and isinstance(c.get("pid"), int) and process_alive(c["pid"])]


def _write(root: Path, commands: list[dict]) -> None:
    path = _file(root)
    if not commands:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps({"commands": commands}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for attempt in range(5):   # Windows：他のコマンドが読んでいる間は置き換えられない
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                temporary.unlink(missing_ok=True)
                raise
            time.sleep(0.05)


@contextmanager
def running(root: Path, command: str) -> Iterator[None]:
    """コマンドを実行している間、その作業空間を使用中にする。書けなくても（読み取り専用等）コマンドは止めない。"""
    token = uuid.uuid4().hex
    try:
        with _changing(root):
            _write(root, _read(root) + [{"id": token, "pid": os.getpid(), "command": command,
                                         "since": datetime.now().astimezone().isoformat(timespec="seconds")}])
        registered = True
    except OSError:
        registered = False
    try:
        yield
    finally:
        if registered:
            try:
                with _changing(root):
                    _write(root, [c for c in _read(root) if c.get("id") != token])
            except OSError:
                pass


def reasons_of(roots: Sequence[Path]) -> list[list[str]]:
    """作業空間ごとの、使っているもの（日本語の文。なければ空）。まとめて調べる。"""
    found = [[f"ecobuild {c.get('command', '')} を実行中です（pid {c['pid']}）" for c in _read(root)] for root in roots]
    for source in _sources:
        for index, texts in enumerate(source(roots)):
            found[index] += texts
    return found


def reasons(root: Path) -> list[str]:
    return reasons_of([Path(root)])[0]
