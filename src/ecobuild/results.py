"""ライブラリの戻り値。CLIはこれを人向けの表示とJSONへ変換する。

作業の進め方の戻り値（作業空間・PR・状態等）は ecowork.workspace にある。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
