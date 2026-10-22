"""このPCにあるモジュールの一覧（modules.json。ツールの設定と同じ場所＝ECOBUILD_HOME）。

元の clone：このPCでモジュールを置く場所（モジュールのclone）。既定のブランチのまま置き、タスクの作業はその中の
作業空間でする。作業空間：<元の clone>/.ecobuild/w/<名前> の git worktree。task start で作り、task finish・drop・
close・workspace close で消える。作業空間は記録せず、そのつど元の clone の git worktree list から読む
（同じブランチは1か所でだけ取り出せる：git の制約）。

記録するのは元の clone の場所だけで、リポジトリ・ブランチ・作業空間は、そのつど読む（名前の変更・作業で古くならない
ように）。前の版が作った、独立した clone の作業空間（モジュールの隣の Calc-1・.ecobuild/ai/team の中 等）は legacy
として分けて出す（自動では消さない。workspace close で閉じる）。

記録するとき：module new・module clone・module adopt、モジュール（作業空間の中でも）でコマンドを実行したとき、
workspace add。外すとき：workspace forget、module delete --remove-workspaces、legacy を workspace close したとき。
フォルダを移動・削除しても記録は消さない（外付けのドライブを外しているだけのこともある）。一覧では「見つからない」と出す。

以前の記録（workspaces.json・clones.json）は読むだけで、消しも書き換えもしない（入っている古い ECOBuild・GUI がまだ
使う）。modules.json がなければ、それらから移す（戻すには modules.json を消せば、また移す）。
"""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from . import config as _config
from . import locks as _locks
from . import settings as _settings
from .errors import EcoBuildError, ErrorCode
from .fsutil import locked

if TYPE_CHECKING:
    from .results import LegacyEntry, TaskWorkspace, WorkspaceEntry, WorkspaceList

FILE_NAME = "modules.json"
VERSION = 1
OLD_FILE_NAMES = ("workspaces.json", "clones.json")   # 以前の記録（読むだけ。新しい記録がなければ移す）
LOCK_NAME = "modules.lock"   # 記録を読んで書き直す間のロック（子タスクを並べて作る等、同時に書くと記録が消える）
AREA = f"{_config.DIRECTORY}/w"   # 元の clone の中の、作業空間の置き場所（git に見せない：info/exclude）
_REVIEW_KEY = "ecowork.review"    # 確認用の作業空間の印（ecowork が作業空間だけの設定に書く）
_ACCOUNT_KEY = "ecowork.account"


@dataclass(frozen=True)
class ModuleRecord:
    """記録した元の clone（modules）・前の版の作業空間（legacy）。repository・url は記録したときのもの（表示はそのつど読む）。"""
    path: Path
    repository: str | None = None
    url: str | None = None


def file() -> Path:
    return _settings.home() / FILE_NAME


def _changing():
    """記録を読んで書き直す間は、ほかのコマンドと1つずつ（読んだ後に書かれたものを消さない）。"""
    return locked(file().with_name(LOCK_NAME), timeout=10)


def _load(*, write: bool = True) -> tuple[list[ModuleRecord], list[ModuleRecord]]:
    """(元の clone, 前の版の作業空間)。記録がなければ以前の記録から移して書く（write：記録を書き直す間〔_changing〕は
    書かない。呼ぶ側が書く）。読めなければ空。"""
    path = file()
    if not path.is_file():
        modules, legacy = _migrate()
        if write and (modules or legacy):
            try:
                with _changing():
                    if not path.is_file():
                        _save(modules, legacy)
            except OSError:
                pass
        return modules, legacy
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], []
    if not isinstance(data, dict):
        return [], []
    return _records(data.get("modules")), _records(data.get("legacy"))


def _records(items) -> list[ModuleRecord]:
    return [ModuleRecord(Path(item["path"]), item.get("repository") or None, item.get("url") or None)
            for item in items or () if isinstance(item, dict) and isinstance(item.get("path"), str)]


def recorded() -> list[ModuleRecord]:
    """記録した元の clone（記録した順）。"""
    return _load()[0]


def legacy() -> list[Path]:
    """前の版の作業空間（独立した clone。記録した順）。"""
    return [item.path for item in _load()[1]]


def _old_recorded() -> list[Path]:
    """以前の記録（workspaces.json、なければ clones.json）の場所。"""
    for name in OLD_FILE_NAMES:
        path = _settings.home() / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        items = data.get("workspaces", data.get("clones", [])) if isinstance(data, dict) else []
        return [Path(item["path"]) for item in items if isinstance(item, dict) and isinstance(item.get("path"), str)]
    return []


def _migrate() -> tuple[list[ModuleRecord], list[ModuleRecord]]:
    """以前の記録（作業空間ごと）から、元の clone の一覧を作る。

    - 作業空間（linked worktree）と、ECOBuild が自分で持っていたもの（ECOBUILD_HOME の中）は飛ばす。
    - ほかのモジュールの .ecobuild/ の中（前の版の作業役の作業空間 等）は legacy。
    - 同じリポジトリの clone が2つ以上あれば、1つを元の clone にし、残りは legacy にする。選び方は今までの GUI と同じ：
      .ecobuild/ の外 → フォルダー名がリポジトリ名と同じ → タスクブランチにいない → 記録した順。
    - 見つからない場所は、そのまま元の clone として残す（workspace forget で外せる）。
    """
    modules: list[ModuleRecord] = []
    legacy_items: list[ModuleRecord] = []
    groups: dict[str, list[tuple[tuple, ModuleRecord]]] = {}
    for order, path in enumerate(_old_recorded()):
        if _in_home(path) or (path / ".git").is_file():
            continue
        if not (path / _config.FILE_NAME).is_file():
            modules.append(ModuleRecord(path))
            continue
        url, branch = _read_origin(path)
        item = ModuleRecord(path, github_name(url) if url else None, url)
        if _inside_other_area(path):
            legacy_items.append(item)
            continue
        name = (item.repository or "").split("/")[-1]
        on_task = bool(branch and branch.startswith("task/"))
        score = (not (name and path.name.casefold() == name.casefold()), on_task, order)
        groups.setdefault(identity(url) or key(path), []).append((score, item))
    for group in groups.values():
        ranked = [item for _, item in sorted(group, key=lambda pair: pair[0])]
        modules.append(ranked[0])
        legacy_items += ranked[1:]
    return modules, legacy_items


def _read_origin(path: Path) -> tuple[str | None, str | None]:
    from ecowork.git import Git
    try:
        git = Git(path)
        return git.get_config("remote.origin.url"), git.current_branch()
    except Exception:   # gitで読めない（壊れたclone 等）
        return None, None


def _in_home(path: Path) -> bool:
    """ECOBuild が自分で持っていた場所（ECOBUILD_HOME の中。前の版の進行役の作業空間 等）。"""
    try:
        return Path(path).resolve().is_relative_to(_settings.home().resolve())
    except OSError:
        return False


def _inside_other_area(root: Path) -> bool:
    """ほかのモジュールの .ecobuild/ の中にある（作業空間 .ecobuild/w/・前の版の作業役の作業空間 等）。"""
    root = Path(root).resolve()
    return any((parent / _config.FILE_NAME).is_file() and root.is_relative_to(parent / _config.DIRECTORY)
               for parent in root.parents)


def is_workspace(path: Path | str) -> bool:
    """path が作業空間（<元の clone>/.ecobuild/w/<名前>）そのものか。"""
    path = Path(path).resolve()
    return (path.parent.name == "w" and path.parent.parent.name == _config.DIRECTORY
            and (path.parent.parent.parent / _config.FILE_NAME).is_file())


def is_managed(path: Path | str) -> bool:
    """path が ECOBuild の置き場所（モジュールの .ecobuild/ の中：作業空間 .ecobuild/w/・前の版の作業役 等）にあるか。
    人が git worktree で作った作業ツリー（モジュールの外・.worktrees/ 等）は False（ECOBuild は消さない）。"""
    return _inside_other_area(Path(path))


def original_of(path: Path | str) -> Path:
    """path（モジュールの場所）の元の clone。作業空間（git worktree）ならその元、ほかはそれ自身。"""
    path = Path(path)
    if (path / ".git").is_file():
        from ecowork.git import Git
        try:
            return Git(path).common_root()
        except Exception:   # gitで読めない（壊れた作業空間 等）。置き場所から分かれば
            if is_workspace(path):
                return path.resolve().parent.parent.parent
    return path


def area(root: Path | str) -> Path:
    """元の clone root の、作業空間の置き場所（.ecobuild/w）。"""
    return Path(root) / AREA


def exclude_area(root: Path | str) -> None:
    """作業空間の置き場所（/.ecobuild/w/）を git に見せない（共通の info/exclude に、なければ1度だけ書く）。"""
    _locks.exclude(Path(root), f"/{AREA}/")


def record(root: Path) -> bool:
    """root（モジュールの場所）の元の clone を記録する。作業空間の中で動いたときは、その元の clone。
    他のモジュールの中にあるもの（依存先のclone 等）・ECOBuild が自分で持つもの（ECOBUILD_HOME の中）・前の版の作業空間
    （legacy）は記録しない。同じリポジトリの元の clone が既にあれば、legacy として記録する。記録を変えたら True。"""
    root = original_of(Path(root)).resolve()
    if nested(root) or _in_home(root):
        return False
    modules, legacy_items = _load()
    if any(same(item.path, root) for item in modules + legacy_items):
        return False
    url, _ = _read_origin(root)
    item = ModuleRecord(root, github_name(url) if url else None, url)
    with _changing():
        modules, legacy_items = _load(write=False)
        if any(same(item.path, root) for item in modules + legacy_items):
            return False
        mine = identity(url)
        if _inside_other_area(root) or (mine is not None and any(
                identity(m.url) == mine and (m.path / _config.FILE_NAME).is_file() for m in modules)):
            _save(modules, legacy_items + [item])
        else:
            _save(modules + [item], legacy_items)
    return True


def record_quietly(root: Path) -> None:
    """コマンドのついでの記録。失敗しても（別のコマンドが同時に書いている等）コマンドは止めない。"""
    try:
        record(root)
    except OSError:
        pass


def forget(path: Path) -> bool:
    """記録（元の clone・前の版の作業空間）から外す（フォルダには触らない）。記録になければ False。"""
    with _changing():
        modules, legacy_items = _load(write=False)
        kept = [item for item in modules if not same(item.path, path)]
        kept_legacy = [item for item in legacy_items if not same(item.path, path)]
        if len(kept) == len(modules) and len(kept_legacy) == len(legacy_items):
            return False
        _save(kept, kept_legacy)
    return True


def is_legacy(root: Path) -> bool:
    """前の版の作業空間（独立した clone）か：記録の legacy にあるか、ほかのモジュールの .ecobuild/ の中にあるか、
    同じリポジトリの別の元の clone を記録しているか。"""
    root = Path(root)
    modules, legacy_items = _load()
    if any(same(item.path, root) for item in legacy_items) or _inside_other_area(root):
        return True
    if any(same(item.path, root) for item in modules):
        return False
    url, _ = _read_origin(root)
    mine = identity(url)
    return mine is not None and any(identity(m.url) == mine and not same(m.path, root)
                                    and (m.path / _config.FILE_NAME).is_file() for m in modules)


def inside(root: Path) -> list[Path]:
    """前からの clone の作業空間 root の .ecobuild/ の中にある、前の版の作業空間（独立した clone。作業役 等）。中の
    作業空間の中にあるものも。root を閉じると一緒に消えるもの。worktree の作業空間（.ecobuild/w/。git worktree list で
    読む：task_workspaces）は数えない。"""
    found = []
    for folder, children, _ in os.walk(Path(root) / _config.DIRECTORY):
        here = Path(folder)
        if (here / ".git").is_dir() and (here / _config.FILE_NAME).is_file():
            found.append(here)
            found += inside(here)
            children.clear()   # 中の作業空間の中は、その作業空間として見た（上で）
        elif here == area(root):
            children.clear()   # worktree の作業空間の置き場所
        else:
            children[:] = [c for c in children if c != ".git"]
    return found


def nested(root: Path) -> bool:
    """他のモジュールの中にある（依存先のclone 等）。ただし、そのモジュールの .ecobuild/ の中（ECOBuild の置き場所。
    作業空間 .ecobuild/w/・前の版の作業役の作業空間 等）は除く。"""
    root = Path(root).resolve()
    return any((parent / _config.FILE_NAME).is_file() and not root.is_relative_to(parent / _config.DIRECTORY)
               for parent in root.parents)


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


def task_workspaces(root: Path) -> list["TaskWorkspace"]:
    """元の clone root の作業空間（.ecobuild/w/ の git worktree。フォルダーがなくなったものは除く）。ロックは調べない。"""
    from ecowork import model as wm
    from ecowork.git import Git

    from .results import TaskWorkspace
    try:
        worktrees = Git(root).worktrees()
    except Exception:   # gitで読めない
        return []
    place = key(area(root))
    found = []
    for worktree in worktrees:
        if worktree.main or worktree.prunable or not key(worktree.path).startswith(place + os.sep):
            continue
        account, review = _workspace_settings(worktree.path)
        found.append(TaskWorkspace(worktree.path.name, worktree.path, worktree.branch,
                                   wm.task_number(worktree.branch) if worktree.branch else None,
                                   account=account, review=review))
    return found


def _workspace_settings(path: Path) -> tuple[str | None, int | None]:
    """作業空間のアカウント（その作業空間だけの設定、なければ共有の設定）と、確認しているPR（作業空間だけの設定）。"""
    from ecowork.git import Git
    try:
        completed = Git(path).run("config", "--show-scope", "--get-regexp", r"^ecowork\.(account|review)$", check=False)
    except Exception:
        return None, None
    account, review = None, None
    for line in completed.stdout.splitlines():
        scope, _, rest = line.partition("\t")
        name, _, value = rest.partition(" ")
        if name == _ACCOUNT_KEY and scope in ("local", "worktree"):
            account = value.strip() or account
        elif name == _REVIEW_KEY and scope == "worktree" and value.strip().isdigit():
            review = int(value.strip())
    return account, review


def listing() -> "WorkspaceList":
    """このPCのモジュール（元の clone と、その中の作業空間）と、前の版の作業空間の今の様子。リポジトリ順（同じリポジトリでは
    場所の順）。ロックの調べ（拡張の docker 等）は、まとめて1回。"""
    from .results import WorkspaceList
    modules, legacy_items = _load()
    with ThreadPoolExecutor(max_workers=8) as pool:   # 場所ごとに git を呼ぶので並べる（順に待つと十数の場所で約2秒）
        found = list(pool.map(module_entry, [item.path for item in modules if not _in_home(item.path)]))
        old = list(pool.map(legacy_entry, [item.path for item in legacy_items]))
    places = [e.path for e in found + old if e.exists] + [w.path for e in found for w in e.workspaces]
    locks = dict(zip(map(key, places), _locks.status_of(places)))
    found = [replace(e, lock=locks[key(e.path)],
                     workspaces=tuple(replace(w, lock=locks[key(w.path)]) for w in e.workspaces)) if e.exists else e
             for e in found]
    old = [replace(e, lock=locks[key(e.path)]) if e.exists else e for e in old]
    order = lambda e: ((e.repository or e.url or "~").casefold(), key(e.path))   # noqa: E731
    return WorkspaceList(tuple(sorted(found, key=order)), tuple(sorted(old, key=order)))


def module_entry(path: Path) -> "WorkspaceEntry":
    """元の clone path の今の様子（中の作業空間も。ロックは調べない）。"""
    from ecowork import model as wm

    from .results import WorkspaceEntry
    if not (path / _config.FILE_NAME).is_file():
        return WorkspaceEntry(path, False)
    url, branch = _read_origin(path)
    return WorkspaceEntry(path, True, github_name(url) if url else None, url, branch,
                          wm.task_number(branch) if branch else None, type=_module_type(path),
                          default_branch=_default_branch(path), workspaces=tuple(task_workspaces(path)))


def legacy_entry(path: Path) -> "LegacyEntry":
    from ecowork import model as wm

    from .results import LegacyEntry
    if not (path / _config.FILE_NAME).is_file():
        return LegacyEntry(path, False)
    url, branch = _read_origin(path)
    return LegacyEntry(path, True, github_name(url) if url else None, url, branch,
                       wm.task_number(branch) if branch else None)


def places() -> list[Path]:
    """このPCのモジュールの場所すべて：元の clone・その中の作業空間・前の版の作業空間（今あるもの）。"""
    modules, legacy_items = _load()
    found = []
    for item in modules:
        if (item.path / _config.FILE_NAME).is_file():
            found += [item.path] + [w.path for w in task_workspaces(item.path)]
    return found + [item.path for item in legacy_items if (item.path / _config.FILE_NAME).is_file()]


def _module_type(root: Path) -> str:
    """モジュールの型（ecobuild.toml の [module] type。読めなければ空）。"""
    return str(_module_table(root).get("type") or "")


def _default_branch(root: Path) -> str:
    """タスクブランチの既定の作成元（ecobuild.toml の [branches] default_base。なければ main。config.load と同じ）。"""
    return str(_module_table(root, "branches").get("default_base") or "main")


def _module_table(root: Path, name: str = "module") -> dict:
    """ecobuild.toml の表 name（読めなければ空）。一覧では壊れたモジュールでも止めないので config.load を使わない。"""
    import tomllib
    try:
        value = tomllib.loads((root / _config.FILE_NAME).read_text(encoding="utf-8")).get(name, {})
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def module_root(path: Path) -> Path:
    """path（か、その上）のモジュールの場所。モジュールでなければ、他のモジュールの中なら誤り。"""
    root = _config.find_root(Path(path))
    if nested(root):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{root} は他のモジュールの中にあります（依存先のclone 等）。",
                            hint="モジュールのclone そのものを指定してください。")
    return root


def _save(modules: list[ModuleRecord], legacy_items: list[ModuleRecord]) -> None:
    path = file()
    path.parent.mkdir(parents=True, exist_ok=True)

    def items(records, *, url: bool):
        return [{"path": item.path.as_posix(), "repository": item.repository, **({"url": item.url} if url else {})}
                for item in records]
    data = {"version": VERSION, "modules": items(modules, url=True), "legacy": items(legacy_items, url=False)}
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
