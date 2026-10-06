"""モジュールの型：言語ごとの処理（ビルド・Project・ファイル・依存先等）を受け持つ拡張の口。

ECOBuildの本体は型の中身を知らない。型は登録ファイル（module_types.toml）に書かれたものだけを使い、
ecobuild.toml の [module] type で選ぶ。同じコマンドでも、型によって中身が変わる。
型が対応しない操作は not_supported で止まる（ModuleType の既定の動き）。
"""

from __future__ import annotations

import importlib
import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .errors import EcoBuildError, ErrorCode

if TYPE_CHECKING:
    from .config import ModuleConfig, Profile
    from .module import Module
    from .results import (BuildResult, DependencyChange, DependencyState, FilesChanged, LinkResult, RunResult,
                          TestResult)
    from .tooling import CheckItem as DoctorItem

REGISTRY = "module_types.toml"


@dataclass(frozen=True)
class TypeEntry:
    """登録ファイルの1つの型。"""
    name: str
    module: str          # 実装のPythonモジュール
    cls: str             # ModuleType の子クラスの名前
    description: str


class ModuleType:
    """型の基底。既定はどの操作も not_supported。型は対応する操作だけを上書きする。

    クラスの属性・クラスメソッドは、モジュールがまだない場面（new・doctor等）で使う。
    インスタンスは1つのモジュール（module）に結び付き、そのモジュールの中で働く。
    """

    name = ""
    description = ""
    generated_note = ""          # 生成ファイルの説明（ヒント・AGENTS.mdに使う）。なければ空

    def __init__(self, module: "Module"):
        self.module = module

    @property
    def root(self) -> Path:
        return self.module.root

    def not_supported(self, operation: str) -> EcoBuildError:
        return EcoBuildError(ErrorCode.NOT_SUPPORTED, f"型 {self.name} は {operation} に対応していません。",
                             hint="ecobuild types で型の一覧を確認できます。")

    # モジュールの作成（モジュールがまだないので、クラスメソッド） ------------------------------

    @classmethod
    def new_config(cls, name: str, *, app: bool) -> "ModuleConfig":
        from .config import ModuleConfig, ProjectNames
        return ModuleConfig(name=name, type=cls.name, projects=ProjectNames(name, name + "Test"))

    @classmethod
    def populate(cls, root: Path, config: "ModuleConfig") -> None:
        """新しいモジュールの中身を作る（ecobuild.toml・README等は本体が作る）。"""

    @classmethod
    def gitignore(cls) -> str:
        return ""

    @classmethod
    def gitattributes(cls) -> str:
        return ""

    @classmethod
    def readme_usage(cls, config: "ModuleConfig") -> str:
        """READMEの「ECOBuildなしで使う」等、型ごとの説明。"""
        return ""

    @classmethod
    def ci_workflow(cls, config: "ModuleConfig") -> str | None:
        """CI（GitHub Actions）のワークフロー。Noneなら CI に対応しない。"""
        return None

    @classmethod
    def doctor_items(cls) -> list["DoctorItem"]:
        """doctor で調べる、型が使うツール。"""
        return []

    # 生成ファイルと、手元をそろえる処理 -----------------------------------------------

    def is_generated(self, path: str) -> bool:
        """管理ファイルから作り直せる生成ファイルか（衝突したら作り直す）。"""
        return False

    def is_managed(self, path: str) -> bool:
        """生成ファイル・管理ファイル（task submit の前にコミット済みであるべきもの）か。"""
        return False

    def refresh(self) -> bool:
        """生成ファイルを作り直す。作り直したらTrue。"""
        return False

    def prepare(self) -> tuple[tuple["DependencyChange", ...], bool]:
        """取り込み・切り替えの後、手元（依存先・生成ファイル）を記録にそろえる。

        （依存先の変化, 生成ファイルを作り直したか）を返す。
        """
        return (), False

    # ビルド ---------------------------------------------------------------------

    def build_options(self, profile: "Profile | None", configuration: str) -> Any:
        """ビルド設定と、指定した構成から、ビルド等に渡す設定を作る（.configuration を持つ）。"""
        raise self.not_supported("ビルド")

    def validate_profile(self, profile: "Profile") -> None:
        raise self.not_supported("ビルド設定")

    def build(self, project: str | None, options: Any, action: str) -> "BuildResult":
        raise self.not_supported(action)

    def test(self, project: str | None, options: Any) -> "TestResult":
        raise self.not_supported("テスト")

    def run(self, project: str | None, options: Any, arguments: str) -> "RunResult":
        raise self.not_supported("実行")

    # Project・ファイル ----------------------------------------------------------------

    def project_at(self, path: Path) -> str | None:
        return None

    def executable_at(self, path: Path) -> str | None:
        return None

    def projects(self) -> tuple:
        raise self.not_supported("Project の一覧")

    def add_project(self, name: str, kind: str) -> "FilesChanged":
        raise self.not_supported("Project の追加")

    def remove_project(self, name: str) -> "FilesChanged":
        raise self.not_supported("Project の削除")

    def set_pch(self, project: str, *, enable: bool) -> "FilesChanged":
        raise self.not_supported("PCH")

    def add_file(self, path: Path, *, test: bool) -> "FilesChanged":
        raise self.not_supported("ファイルの追加")

    def remove_file(self, path: Path, *, test: bool) -> "FilesChanged":
        raise self.not_supported("ファイルの削除")

    def move_file(self, source: Path, destination: Path, *, test: bool) -> "FilesChanged":
        raise self.not_supported("ファイルの移動")

    # 依存先 ------------------------------------------------------------------------

    def link(self, url: str, *, project: str | None, shared: bool) -> "LinkResult":
        raise self.not_supported("依存先")

    def unlink(self, name: str) -> "LinkResult":
        raise self.not_supported("依存先")

    def dependencies(self) -> tuple["DependencyState", ...]:
        return ()

    def update_dependencies(self, name: str | None) -> tuple["DependencyChange", ...]:
        raise self.not_supported("依存先")

    def sync_dependencies(self) -> tuple["DependencyChange", ...]:
        return ()


# 登録 ----------------------------------------------------------------------------

def entries() -> dict[str, TypeEntry]:
    """登録ファイルにある型（名前 → 登録の内容）。"""
    text = (resources.files("ecobuild") / REGISTRY).read_text(encoding="utf-8")
    data = tomllib.loads(text)
    return {name: TypeEntry(name, table["module"], table["class"], table.get("description", ""))
            for name, table in data.items()}


def load(name: str) -> type[ModuleType]:
    """型の名前から、型のクラスを読み込む。"""
    registered = entries()
    if name not in registered:
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"型 {name} は登録されていません。",
                            hint="登録済みの型：" + "、".join(registered) + "（ecobuild types）")
    entry = registered[name]
    try:
        cls = getattr(importlib.import_module(entry.module), entry.cls)
    except (ImportError, AttributeError) as error:
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"型 {name} の実装（{entry.module}.{entry.cls}）を読み込めません。",
                            details=f"{type(error).__name__}: {error}") from error
    if not (isinstance(cls, type) and issubclass(cls, ModuleType)):
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"型 {name} の実装は ModuleType の子クラスではありません。")
    return cls


def available() -> list[type[ModuleType]]:
    """読み込める登録済みの型（doctor 等、モジュールの外で使う）。"""
    result = []
    for name in entries():
        try:
            result.append(load(name))
        except EcoBuildError:
            continue
    return result
