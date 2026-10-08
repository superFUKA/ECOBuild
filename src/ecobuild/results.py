"""ライブラリの戻り値。CLIはこれを人向けの表示とJSONへ変換する。

作業の進め方の戻り値（作業空間・PR・状態等）は ecowork.workspace にある。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple, Protocol


@dataclass(frozen=True)
class ModuleCreated:
    name: str
    root: Path
    remote_url: str
    projects: tuple[str, ...]


@dataclass(frozen=True)
class DependencyChange:
    name: str
    action: str                      # cloned / aligned / unchanged / skipped
    reason: str | None = None


class PrepareResult(NamedTuple):
    """型の prepare（取り込み・切り替えの後に手元をそろえる）の結果。"""
    dependencies: tuple[DependencyChange, ...]   # 依存先の変化
    regenerated: bool                            # 生成ファイルを作り直したか


@dataclass(frozen=True)
class ProjectSummary:
    """Projectの一覧（型の projects）の1件。CLIの表示とJSONはこの形を使う。"""
    name: str
    kind: str                 # 種類（型が決める。cpp：static_library / executable / test 等）
    directory: str            # モジュールからの相対
    links: tuple[str, ...]    # リンクしているProjectと依存先のモジュール


class BuildOptions(Protocol):
    """型の build_options が返すビルド設定のうち、本体が読むもの（それ以外は型が決める）。"""
    configuration: str


@dataclass(frozen=True)
class DependencyState:
    name: str
    url: str
    recorded: str                    # 記録された版（コミット）
    local: str | None                # 手元のcloneの版（なければNone）
    state: str                       # aligned / differs / modified / working / missing
    branch: str | None = None        # 作業版ならそのブランチ


@dataclass(frozen=True)
class LinkResult:
    name: str                        # 依存先の名前（deps/<名前>）
    url: str
    revision: str
    projects: tuple[str, ...]        # リンクした（外した）Project
    clone_removed: bool = False      # unlink：手元のcloneを消したか（作業中・変更ありなら残す）


@dataclass(frozen=True)
class CiInitResult:
    path: str
    private_dependencies: tuple[str, ...]   # CIで取得するにはトークンが要る依存先


@dataclass(frozen=True)
class CheckItem:
    name: str                        # generated / conflict_markers / build / test
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class CheckReport:
    items: tuple[CheckItem, ...]

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.items)


@dataclass(frozen=True)
class ModuleCloned:
    name: str
    root: Path
    remote_url: str
    projects: tuple[str, ...]
    dependencies: tuple[DependencyChange, ...]


@dataclass(frozen=True)
class SyncResult:
    branch: str
    merged: tuple[str, ...]          # 取り込んだ（または早送りした）参照。sync continueでは merge／rebase
    dependencies: tuple[DependencyChange, ...]
    regenerated: bool


@dataclass(frozen=True)
class BuildResult:
    project: str | None              # Noneは全体
    configuration: str
    artifacts: tuple[str, ...]
    profile: str | None = None       # 使った名前付きビルド設定
    action: str = "build"            # build / clean / rebuild


@dataclass(frozen=True)
class ProfileList:
    profiles: dict                   # 名前 → Profile
    selected: str | None             # このPCで選んでいる設定（ecobuild.local.toml）


@dataclass(frozen=True)
class FilesChanged:
    """ファイル・Projectの操作で変わったファイル（モジュールからの相対パス）。"""
    action: str
    paths: tuple[str, ...]
    project: str | None = None


@dataclass(frozen=True)
class TestCaseResult:
    name: str
    status: str


@dataclass(frozen=True)
class TestResult:
    project: str | None
    configuration: str
    passed: int
    failed: int
    skipped: int
    cases: tuple[TestCaseResult, ...]


@dataclass(frozen=True)
class RunResult:
    project: str | None
    configuration: str
    returncode: int
    output: str
