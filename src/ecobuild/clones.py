"""このPCにある、モジュールのclone の記録（clones.json。ツールの設定と同じ場所＝ECOBUILD_HOME）。

GitHubの情報（module list）とは別に、手元のどこにcloneがあるかだけを持つ。記録するのは場所と種類だけで、
リポジトリ・ブランチ・作業中のタスクは、そのつどclone から読む（名前の変更・切り替えで古くならないように）。

記録するとき：module new・module clone・task start --dir で作ったとき、モジュールの中でコマンドを実行したとき
（以前からあるclone も、使えば記録される）、module register。外すとき：module forget、module delete --remove-clone。
フォルダを移動・削除しても記録は消さない（外付けのドライブを外しているだけのこともある）。一覧では「見つからない」と出す。
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from . import config as _config
from .errors import EcoBuildError, ErrorCode

if TYPE_CHECKING:
    from .results import CloneEntry

FILE_NAME = "clones.json"
MODULE = "module"         # モジュールのclone
WORKSPACE = "workspace"   # 作業空間専用のclone（task start --dir）
KINDS = (MODULE, WORKSPACE)


@dataclass(frozen=True)
class Recorded:
    path: Path
    kind: str


def file() -> Path:
    from . import settings
    return settings.home() / FILE_NAME


def recorded() -> list[Recorded]:
    """記録の一覧（記録した順）。読めなければ空。"""
    try:
        data = json.loads(file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = data.get("clones", []) if isinstance(data, dict) else []
    return [Recorded(Path(item["path"]), item.get("kind") if item.get("kind") in KINDS else MODULE)
            for item in items if isinstance(item, dict) and isinstance(item.get("path"), str)]


def record(root: Path, kind: str | None = None) -> bool:
    """root（モジュールのclone）を記録する。kind を省くと、記録済みなら種類を変えず、新しければモジュールのclone。
    他のモジュールの中にあるもの（依存先のclone 等）は記録しない。記録を変えたら True。"""
    root = Path(root).resolve()
    if nested(root):
        return False
    items = recorded()
    for i, item in enumerate(items):
        if same(item.path, root):
            if kind is None or item.kind == kind:
                return False
            items[i] = Recorded(item.path, kind)
            break
    else:
        items.append(Recorded(root, kind or MODULE))
    _save(items)
    return True


def record_quietly(root: Path, kind: str | None = None) -> None:
    """コマンドのついでの記録。失敗しても（別のコマンドが同時に書いている等）コマンドは止めない。"""
    try:
        record(root, kind)
    except OSError:
        pass


def forget(path: Path) -> bool:
    """記録から外す（フォルダには触らない）。記録になければ False。"""
    items = recorded()
    kept = [item for item in items if not same(item.path, path)]
    if len(kept) == len(items):
        return False
    _save(kept)
    return True


def nested(root: Path) -> bool:
    """他のモジュールの中にある（依存先のclone 等）。"""
    return any((parent / _config.FILE_NAME).is_file() for parent in Path(root).resolve().parents)


def same(a: Path | str, b: Path | str) -> bool:
    return key(a) == key(b)


def key(path: Path | str) -> str:
    return os.path.normcase(str(Path(path).resolve()))


def identity(url: str | None) -> str | None:
    """同じリポジトリのclone かを比べる値：GitHubなら 所有者/名前、それ以外は URL（小文字・末尾の .git を除く）。"""
    if not url:
        return None
    name = github_name(url)
    return (name or url.rstrip("/").removesuffix(".git")).casefold()


def github_name(url: str) -> str | None:
    """origin の URL が GitHub のものなら、その 所有者/名前。"""
    match = re.search(r"github\.com[:/]+([^/]+/[^/]+?)(?:\.git)?/?$", url)
    return match.group(1) if match else None


def entries() -> list["CloneEntry"]:
    """記録したcloneの今の様子。リポジトリ順（同じリポジトリでは、モジュールのclone が先）。"""
    found = [entry(item) for item in recorded()]
    return sorted(found, key=lambda e: ((e.repository or e.url or "~").casefold(), e.kind != MODULE,
                                        key(e.path)))


def entry(item: Recorded) -> "CloneEntry":
    from ecowork import workspace as ws
    from ecowork.git import Git

    from .results import CloneEntry
    if not (item.path / _config.FILE_NAME).is_file():
        return CloneEntry(item.path, item.kind, False)
    git = Git(item.path)
    try:
        url, branch = git.get_config("remote.origin.url"), git.current_branch()
    except Exception:   # gitで読めない（壊れたclone 等）。場所と種類だけ出す
        url, branch = None, None
    return CloneEntry(item.path, item.kind, True, github_name(url) if url else None, url, branch,
                      ws.workspace_number(branch) if branch else None)


def module_root(path: Path) -> Path:
    """path（か、その上）のモジュールの場所。モジュールでなければ、他のモジュールの中なら誤り。"""
    root = _config.find_root(Path(path))
    if nested(root):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{root} は他のモジュールの中にあります（依存先のclone 等）。",
                            hint="モジュールのclone そのものを指定してください。")
    return root


def _save(items: list[Recorded]) -> None:
    path = file()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"clones": [{"path": item.path.as_posix(), "kind": item.kind} for item in items]}
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for attempt in range(5):   # Windows：他のコマンドが読んでいる間は置き換えられない
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                temporary.unlink(missing_ok=True)
                raise
            time.sleep(0.05)
