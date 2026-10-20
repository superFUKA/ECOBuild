"""モジュールの型：言語ごとの処理（ビルド・Project・ファイル・依存先等）を受け持つ拡張の口。

ECOBuildの本体は型の中身を知らない。型は使う側が Registry に登録して Module に渡し（外部から型を足せる）、
ecobuild.toml の [module] type で選ぶ。同じ操作でも、型によって中身が変わる。

型は ModuleType（どの型にもあるもの）を継承し、持つ能力（Builds・HasProjects・HasFiles・HasDependencies）だけを
足す。持たない能力の操作は、Module が not_supported で止める。言語だけの操作（C++のPCH等）は型の口に置かず、
拡張が自分の公開APIとして出す。
"""

from __future__ import annotations

import importlib
import tomllib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from .errors import EcoBuildError, ErrorCode, operation

if TYPE_CHECKING:
    from .config import ModuleConfig, Profile
    from .module import Module
    from .results import (BuildOptions, BuildResult, DependencyChange, DependencyState, DependencyTree, FilesChanged,
                          LinkResult, PrepareResult, ProjectSummary, RunResult, TestResult)
    from .results import DoctorItem


class ModuleType:
    """型の基底：どの型にもあるもの（作成・生成ファイル・手元をそろえる処理・CI・このPCの準備・型の設定）。

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
                             hint=f"{self.module.op('module types')} で型の一覧を確認できます。")

    # モジュールの作成（モジュールがまだないので、クラスメソッド） ------------------------------

    # module new の --kind で選べる、最初に作るものと既定（型が使わなければ空。--kind を指定すると誤り）
    new_kinds: tuple[str, ...] = ()
    default_new_kind: str | None = None

    @classmethod
    def new_config(cls, name: str) -> "ModuleConfig":
        from .config import ModuleConfig
        return ModuleConfig.for_new_module(name, cls.name)

    @classmethod
    def check_new(cls, name: str, kind: str | None, project: str | None = None, *, test: bool = True) -> None:
        """populate で作れるか（名前等）を、GitHubのリポジトリを作る前に確かめる。作れなければ EcoBuildError。"""

    @classmethod
    def populate(cls, root: Path, config: "ModuleConfig", kind: str | None, project: str | None = None, *,
                 test: bool = True) -> None:
        """新しいモジュールの中身を作る（ecobuild.toml・README等は本体が作る）。kind：new_kinds のどれか。
        project：最初に作るProjectの名前（None ならモジュール名。new_kinds のある型だけに渡る）。
        test：ライブラリのテスト（C++ ならテスト用のProject）も作る。"""

    @classmethod
    def gitignore(cls) -> str:
        return ""

    @classmethod
    def tracked_patterns(cls) -> tuple[str, ...]:
        """管理するファイルの既定のパターン（新しいファイルのうち、task commit が自動で含めるもの。tracking）。
        ECOBuild が作るファイル・型の管理ファイル（is_managed）は、ここに書かなくても常に含める。"""
        return ()

    @classmethod
    def gitattributes(cls) -> str:
        return ""

    @classmethod
    def readme_usage(cls, config: "ModuleConfig") -> str:
        """READMEの「ビルド」等、型ごとの最低限の使い方（Markdown、## の見出しから）。"""
        return ""

    @classmethod
    def ci_workflow(cls, config: "ModuleConfig") -> str | None:
        """CI（GitHub Actions）のワークフロー。Noneなら CI に対応しない。設定は config.ci（[ci]）。"""
        return None

    # このPCの準備（モジュールの外で使うので、クラスメソッド） ----------------------------------

    @classmethod
    def doctor_items(cls) -> list["DoctorItem"]:
        """doctor で調べる、型が使うツール（足りなければ、導入コマンドを install に入れる）。"""
        return []

    @classmethod
    def tool_settings(cls) -> dict[str, str]:
        """ecobuild config で設定できる、型が使うツールの項目（名前 → 説明。例：cpp の cmake）。"""
        return {}

    @classmethod
    def container_packages(cls) -> tuple[str, ...]:
        """作業空間のコンテナ（Ubuntu）に入れる、型が使うツールのパッケージ（apt の名前）。container_dockerfile の材料。"""
        return ()

    @classmethod
    def container_dockerfile(cls) -> str:
        """モジュールのコンテナの環境のひな型（.ecobuild/container/Dockerfile。モジュールを作るときに置き、その後は
        モジュールのもの：解析ツール等を足してよい）。ここにはモジュールで要るものだけを書く。ECOBuild 自身（エージェント・
        ecobuild 等）は、ECOBuild がイメージを作るときに上に重ねる。既定は Ubuntu に container_packages を入れる。"""
        lines = ["# このモジュールの作業空間のコンテナの環境（ECOBuild がこれを元にイメージを作る）。",
                 "# モジュールで要るツールをここに足す。ECOBuild 自身（エージェント・ecobuild 等）は ECOBuild が上に重ねるので書かない。",
                 "# apt の使える Ubuntu・Debian を元にする（ECOBuild の層が apt と uid 1000 の利用者を使う）。",
                 "FROM ubuntu:24.04"]
        if packages := cls.container_packages():
            lines += ["RUN apt-get update \\",
                      f" && DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends {' '.join(packages)} \\",
                      " && rm -rf /var/lib/apt/lists/*"]
        return "\n".join(lines) + "\n"

    @classmethod
    def container_caches(cls) -> tuple[str, ...]:
        """作業空間のコンテナで、作業空間（このPCのフォルダ）ではなくコンテナの側に置くフォルダ（ルートからの場所）。
        ビルドの出力・仮想環境など：このPCのフォルダは中から権限（chmod）を変えられず、ツールが止まることがある
        （CMake の configure_file 等）。速くもなり、このPCのビルドの出力とも混ざらない。"""
        return ()

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

    def prepare(self) -> "PrepareResult":
        """取り込み・切り替えの後、手元（依存先・生成ファイル）を記録にそろえる。"""
        from .results import PrepareResult
        return PrepareResult((), False)

    # 型が決める形の設定（辞書。本体は中身を知らない） --------------------------------------

    def module_settings(self) -> dict:
        """モジュール全体の設定（cpp：main_project・ソリューションフォルダー・テンプレート）。"""
        raise self.not_supported("モジュールの設定")

    def set_module_settings(self, **changes) -> dict:
        raise self.not_supported("モジュールの設定")


# 能力 ---------------------------------------------------------------------------

class Builds(ABC):
    """ビルド・テスト・実行ができる型。"""

    @abstractmethod
    def build_options(self, profile: "Profile | None", configuration: str) -> "BuildOptions":
        """ビルド設定と、指定した構成から、ビルド等に渡す設定を作る（本体は .configuration を読む。他は型が決める）。"""

    @abstractmethod
    def validate_profile(self, profile: "Profile") -> None:
        """名前付きビルド設定を確かめる（誤りなら EcoBuildError）。"""

    @abstractmethod
    def build(self, project: str | None, options: Any, action: str) -> "BuildResult":
        """action：build・clean・rebuild。"""

    @abstractmethod
    def test(self, project: str | None, options: Any) -> "TestResult":
        ...

    @abstractmethod
    def run(self, project: str | None, options: Any, arguments: str) -> "RunResult":
        ...

    def executable_at(self, path: Path) -> str | None:
        """path にある実行ファイルのProject（なければNone）。"""
        return None


class HasProjects(ABC):
    """モジュールの中に Project（小さな開発単位）を持つ型。Projectの設定は型が決める形の辞書。"""

    @abstractmethod
    def project_at(self, path: Path) -> str | None:
        ...

    @abstractmethod
    def projects(self) -> "tuple[ProjectSummary, ...]":
        """Projectの一覧。results.ProjectSummary の形で返す（CLIの表示とJSONに使う）。"""

    @abstractmethod
    def add_project(self, name: str, kind: str, *, link: str | None, test: bool) -> "FilesChanged":
        ...

    @abstractmethod
    def remove_project(self, name: str) -> "FilesChanged":
        ...

    @abstractmethod
    def move_project(self, name: str, destination: str) -> "FilesChanged":
        ...

    @abstractmethod
    def project_details(self, name: str) -> dict:
        """Projectの設定すべて。"""

    @abstractmethod
    def set_project(self, name: str, **changes) -> dict:
        ...

    @abstractmethod
    def link_project(self, name: str, library: str, *, as_type: str | None) -> dict:
        """同じモジュールのProjectをリンクする。"""

    @abstractmethod
    def unlink_project(self, name: str, link: str) -> dict:
        ...


class HasFiles(ABC):
    """ファイルの追加・削除・移動を受け持つ型（テストを一緒に作るか等の方針も型が決める）。"""

    @abstractmethod
    def add_file(self, path: Path, *, test: bool, template: str | None = None) -> "FilesChanged":
        ...

    def add_files(self, paths: list[Path], *, test: bool, template: str | None = None) -> list["FilesChanged"]:
        """まとめて足す（型が順序や組を決めてよい。既定は指定の順に1つずつ）。"""
        return [self.add_file(path, test=test, template=template) for path in paths]

    @abstractmethod
    def remove_file(self, path: Path, *, test: bool) -> "FilesChanged":
        ...

    @abstractmethod
    def move_file(self, source: Path, destination: Path, *, test: bool) -> "FilesChanged":
        ...

    def add_test(self, path: Path, destination: Path | None = None, *, dry_run: bool = False) -> "FilesChanged":
        """今あるファイルのテストを作る（destination：置く場所。既定は型が決める。dry_run：作らずに場所だけ）。
        テストを作らない型は not_supported。"""
        raise self.not_supported("テストの作成")   # type: ignore[attr-defined]   (ModuleType と一緒に継承する)


class HasDependencies(ABC):
    """他のモジュール（GitHubのリポジトリ）を依存先にできる型。"""

    module: "Module"

    @abstractmethod
    def link(self, url: str, *, project: str | None, shared: bool) -> "LinkResult":
        ...

    @abstractmethod
    def unlink(self, name: str) -> "LinkResult":
        ...

    @abstractmethod
    def dependencies(self) -> tuple["DependencyState", ...]:
        ...

    def all_dependencies(self) -> tuple["DependencyState", ...]:
        """依存先の依存先も含めた状態（via に記録している依存先）。既定は、直接の依存先だけ。"""
        return self.dependencies()

    def dependency_tree(self) -> "DependencyTree":
        """依存関係の図（依存先の依存先も）。既定は、直接の依存先だけ（その先は分からない）。"""
        from .results import DependencyNode, DependencyTree
        direct = self.dependencies()
        return DependencyTree(self.module.name, tuple(d.name for d in direct),
                              tuple(DependencyNode(d.name, d.url, d.recorded, d.local is not None, ()) for d in direct))

    @abstractmethod
    def update_dependencies(self, name: str | None) -> tuple["DependencyChange", ...]:
        ...

    @abstractmethod
    def sync_dependencies(self) -> tuple["DependencyChange", ...]:
        ...


# 登録 ----------------------------------------------------------------------------

@dataclass(frozen=True)
class TypeEntry:
    """登録した1つの型。実装（module・cls）は、使うときに初めて読み込む（読み込めない型があっても他の型は使える）。"""
    name: str
    module: str          # 実装のPythonモジュール
    cls: str             # ModuleType の子クラスの名前
    description: str = ""


class Registry:
    """使えるモジュールの型の集まり。本体は型を知らず、使う側（拡張を入れた層等）が型を登録して Module に渡す。

    default：型を指定せずにモジュールを作るときの型（なければ指定が要る）。
    """

    def __init__(self, entries: Iterable[TypeEntry | type[ModuleType]] = (), *, default: str | None = None):
        self._entries: dict[str, TypeEntry] = {}
        self._loaded: dict[str, type[ModuleType]] = {}
        for entry in entries:
            self.add(entry)
        self.default = default

    def add(self, entry: TypeEntry | type[ModuleType]) -> None:
        """型を登録する。ModuleType の子クラスか、実装の場所（TypeEntry。使うときに読み込む）。"""
        if isinstance(entry, type):
            _check_class(entry.name, entry)
            self._loaded[entry.name] = entry
            entry = TypeEntry(entry.name, entry.__module__, entry.__qualname__, entry.description)
        else:
            self._loaded.pop(entry.name, None)
        self._entries[entry.name] = entry

    @classmethod
    def from_toml(cls, text: str, *, default: str | None = None) -> "Registry":
        """登録ファイル（TOML。[<型の名前>] に module・class・description）から作る。"""
        data = tomllib.loads(text)
        return cls((TypeEntry(name, table["module"], table["class"], table.get("description", ""))
                    for name, table in data.items()), default=default)

    def entries(self) -> dict[str, TypeEntry]:
        """登録した型（名前 → 登録の内容）。"""
        return dict(self._entries)

    def load(self, name: str | None = None, *, command: str = "") -> type[ModuleType]:
        """型の名前（省略時は既定の型）から、型のクラスを読み込む。command：ヒントに書くプログラム名。"""
        name = name or self.default
        registered = "、".join(self._entries) or "なし"
        if not name:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "モジュールの型を指定してください。",
                                hint=f"登録済みの型：{registered}（{operation(command, 'module types')}）")
        if name in self._loaded:
            return self._loaded[name]
        if name not in self._entries:
            raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"型 {name} は登録されていません。",
                                hint=f"登録済みの型：{registered}（{operation(command, 'module types')}）")
        entry = self._entries[name]
        try:
            loaded = getattr(importlib.import_module(entry.module), entry.cls)
        except (ImportError, AttributeError) as error:
            raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"型 {name} の実装（{entry.module}.{entry.cls}）を読み込めません。",
                                details=f"{type(error).__name__}: {error}") from error
        _check_class(name, loaded)
        self._loaded[name] = loaded
        return loaded

    def available(self) -> list[type[ModuleType]]:
        """読み込める登録済みの型（doctor 等、モジュールの外で使う）。"""
        result = []
        for name in self._entries:
            try:
                result.append(self.load(name))
            except EcoBuildError:
                continue
        return result


def _check_class(name: str, loaded: object) -> None:
    if not (isinstance(loaded, type) and issubclass(loaded, ModuleType)):
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"型 {name} の実装は ModuleType の子クラスではありません。")
