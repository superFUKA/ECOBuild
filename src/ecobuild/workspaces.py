"""このPCにある作業空間の記録（workspaces.json。ツールの設定と同じ場所＝ECOBUILD_HOME）。

作業空間：このPCでモジュールの作業をする場所（モジュールのclone）。clone すれば作業空間になり、タスクを開始すると
そこにタスクブランチが置かれる。タスクが終わっても作業空間のまま残り、閉じる（workspace close・task finish
--close-workspace）と ECOBuild が場所ごと消す。作業空間の中は ECOBuild が管理する場所として扱う。

GitHubの情報（module list）とは別に、手元のどこに作業空間があるかだけを持つ。記録するのは場所だけで、
リポジトリ・ブランチ・作業中のタスクは、そのつど作業空間から読む（名前の変更・切り替えで古くならないように）。

記録するとき：module new・module clone・task start --dir で作ったとき、モジュールの中でコマンドを実行したとき
（以前からあるclone も、使えば記録される）、workspace add。外すとき：workspace forget・workspace close、
module delete --remove-workspaces。フォルダを移動・削除しても記録は消さない（外付けのドライブを外しているだけのことも
ある）。一覧では「見つからない」と出す。
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
    from .results import WorkspaceEntry

FILE_NAME = "workspaces.json"
OLD_FILE_NAME = "clones.json"   # 以前の記録（種類つき）。新しい記録がなければ読み、次に書くときに移す


@dataclass(frozen=True)
class Recorded:
    path: Path


def file() -> Path:
    from . import settings
    return settings.home() / FILE_NAME


def recorded() -> list[Recorded]:
    """記録の一覧（記録した順）。読めなければ空。"""
    path = file()
    if not path.is_file() and path.with_name(OLD_FILE_NAME).is_file():
        path = path.with_name(OLD_FILE_NAME)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = (data.get("workspaces", data.get("clones", [])) if isinstance(data, dict) else [])
    return [Recorded(Path(item["path"])) for item in items
            if isinstance(item, dict) and isinstance(item.get("path"), str)]


def record(root: Path) -> bool:
    """root（モジュールのclone）を作業空間として記録する。他のモジュールの中にあるもの（依存先のclone 等）は
    記録しない。記録を変えたら True。"""
    root = Path(root).resolve()
    if nested(root):
        return False
    items = recorded()
    if any(same(item.path, root) for item in items):
        return False
    _save(items + [Recorded(root)])
    return True


def record_quietly(root: Path) -> None:
    """コマンドのついでの記録。失敗しても（別のコマンドが同時に書いている等）コマンドは止めない。"""
    try:
        record(root)
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


def entries() -> list["WorkspaceEntry"]:
    """記録した作業空間の今の様子。リポジトリ順（同じリポジトリでは場所の順）。"""
    found = [entry(item) for item in recorded()]
    return sorted(found, key=lambda e: ((e.repository or e.url or "~").casefold(), key(e.path)))


def entry(item: Recorded) -> "WorkspaceEntry":
    from ecowork import model as wm
    from ecowork.git import Git

    from .results import WorkspaceEntry
    if not (item.path / _config.FILE_NAME).is_file():
        return WorkspaceEntry(item.path, False)
    git = Git(item.path)
    try:
        url, branch = git.get_config("remote.origin.url"), git.current_branch()
    except Exception:   # gitで読めない（壊れたclone 等）。場所だけ出す
        url, branch = None, None
    return WorkspaceEntry(item.path, True, github_name(url) if url else None, url, branch,
                      wm.task_number(branch) if branch else None, type=_module_type(item.path))


def _module_type(root: Path) -> str:
    """作業空間のモジュールの型（ecobuild.toml の [module] type。読めなければ空）。"""
    import tomllib
    try:
        value = tomllib.loads((root / _config.FILE_NAME).read_text(encoding="utf-8")).get("module", {}).get("type")
    except (OSError, tomllib.TOMLDecodeError):
        return ""
    return value if isinstance(value, str) else ""


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
    data = {"workspaces": [{"path": item.path.as_posix()} for item in items]}
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for attempt in range(5):   # Windows：他のコマンドが読んでいる間は置き換えられない
        try:
            temporary.replace(path)
            path.with_name(OLD_FILE_NAME).unlink(missing_ok=True)   # 以前の記録は移し終えた
            return
        except PermissionError:
            if attempt == 4:
                temporary.unlink(missing_ok=True)
                raise
            time.sleep(0.05)
