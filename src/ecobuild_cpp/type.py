"""型 cpp：Project・ファイル・ビルド・テスト・依存先を、CppBuildで扱う。

本体の型の口（ModuleType と能力）を実装する。C++だけの操作（PCH・ファイルテンプレート・CMakeのパッケージ／ソース・
ビルド済みファイルのリンク）は型の口にないので、この型の公開メソッドとして出す（ecobuild_cpp.cpp(module) から使う）。
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from importlib import metadata
from pathlib import Path

from ecowork import model as wm
from ecowork.git import Git

from ecobuild import ci_workflow
from ecobuild.config import ModuleConfig, Profile
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.fsutil import remove_tree
from ecobuild.module_type import Builds, HasDependencies, HasFiles, HasProjects, ModuleType
from ecobuild.results import (BuildResult, DependencyChange, DependencyNode, DependencyState, DependencyTree,
                              FilesChanged, LinkResult, PrepareResult, ProjectSummary, RunResult, TestCaseResult,
                              TestResult)

from . import _cppbuild, _settings


# 名前付きビルド設定の、型 cpp の項目（[profiles.<名前>] の configuration・shared・parallel 以外）：
# 名前 → (値の型, 使える値。None は何でも)。値の意味は _cppbuild.BuildOptions
_POSITIVE = range(1, 1 << 16)
PROFILE_OPTIONS = {
    "architecture": (str, _cppbuild.ARCHITECTURES),
    "cpp_standard": (int, _cppbuild.CPP_STANDARDS),
    "generator": (str, _cppbuild.GENERATORS),
    "toolset": (str, None),
    "c_compiler": (str, None),
    "cxx_compiler": (str, None),
    "toolchain_file": (str, None),
    "windows_sdk": (str, None),
    "test_parallel": (int, _POSITIVE),
    "test_continue_on_failure": (bool, None),
    "googletest_archive": (str, None),
    "fetch_git": (bool, None),
}
# Projectごとの上書き（[profiles.<名前>.projects.<Project>]）。値の意味は _cppbuild.ProjectOptions
PROFILE_PROJECT_OPTIONS = {
    "type": (str, tuple(_cppbuild.LIBRARY_TYPES)),
    "cpp_standard": (int, _cppbuild.CPP_STANDARDS),
    "artifact_directory": (str, None),
    "test_parallel": (int, _POSITIVE),
    "googletest_archive": (str, None),
}


def _check_options(values: dict, known: dict, where: str) -> None:
    for key, value in values.items():
        if key not in known:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{where}に {key} という項目はありません。",
                                hint=f"使える項目：{'・'.join(known)}")
        kind, allowed = known[key]
        if type(value) is not kind or (kind is str and not value) or (allowed is not None and value not in allowed):
            if allowed is None:
                choices = {str: "空でない文字列", int: "整数", bool: "true／false"}[kind]
            else:
                choices = f"{allowed.start}以上の整数" if isinstance(allowed, range) else "・".join(map(str, allowed))
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{where}の {key} に {value!r} は使えません。",
                                hint=f"使える値：{choices}")

GITIGNORE = """\
# 依存先のclone・ビルドの中間ファイル
/deps/
/build/

# CppBuildの中間ファイル・成果物
/.ecobuild/.cppbuild/output/
"""


# 管理するファイルの既定（ソース・ヘッダー・文書）。CppBuildの管理ファイル（.cppbuild/）・生成ファイルは別に常に含める
TRACKED_PATTERNS = ("*.h", "*.hh", "*.hpp", "*.hxx", "*.inl", "*.ipp", "*.c", "*.cc", "*.cpp", "*.cxx", "*.ixx",
                    "*.cppm", "*.md")


def _cppbuild_version() -> str:
    try:
        distribution = metadata.distribution("cppbuild")
        return distribution.read_text("direct_url.json") or distribution.version
    except metadata.PackageNotFoundError:
        return ""


# 足りないツールの導入コマンド（ecobuild setup --install。OS → ツール → コマンド）
INSTALL = {
    "nt": {
        "cmake": ("winget", "install", "--id", "Kitware.CMake", "--exact", "--silent"),
        "compiler": ("winget", "install", "--id", "Microsoft.VisualStudio.2022.BuildTools", "--exact", "--silent",
                     "--override", "--quiet --wait --add Microsoft.VisualStudio.Workload.VCTools "
                                   "--includeRecommended"),
    },
    "posix": {
        "cmake": ("sudo", "apt-get", "install", "--yes", "cmake", "ninja-build"),
        "compiler": ("sudo", "apt-get", "install", "--yes", "g++"),
    },
}


def _install(tool: str) -> tuple[str, ...]:
    return INSTALL["nt" if os.name == "nt" else "posix"][tool]


def _fingerprint(root: Path) -> str:
    """CppBuildの update の結果を左右するものの要約。"""
    digest = hashlib.sha256(_cppbuild_version().encode("utf-8"))
    for directory, children, files in os.walk(root):
        relative = Path(directory).relative_to(root)
        parts = relative.parts
        # .git、ビルドの中間ファイル（build/、依存先の build/）、CppBuildの出力・ロック（.cppbuild/output・operations）は見ない
        children[:] = sorted(c for c in children
                             if c != ".git"
                             and not (c == _cppbuild.BUILD_DIRECTORY
                                      and (parts == () or (len(parts) == 2 and parts[0] == _cppbuild.DEPENDENCY_DIRECTORY)))
                             and not (c in ("output", "operations") and parts[-1:] == (_cppbuild.CONFIG_NAME,)))
        for name in sorted(files):
            # .cppbuild の中（管理ファイル・生成ファイル。依存先のものも）だけ。ソースの一覧は生成ファイルに書かれない
            # （CMakeがビルドのたびに集める）ので、ソースは見ない
            if _cppbuild.CONFIG_NAME in parts:
                path = relative / name
                digest.update(path.as_posix().encode("utf-8") + b"\0")
                digest.update((root / path).read_bytes())
    return digest.hexdigest()


class CppType(ModuleType, Builds, HasProjects, HasFiles, HasDependencies):
    name = "cpp"
    description = "C++。CppBuildでProject・ファイル・ビルド・テスト・依存先を管理する"
    generated_note = (f"CppBuildの生成ファイル（{_cppbuild.CONFIG_DIRECTORY}/ の中の "
                      f"{'・'.join(_cppbuild.GENERATED_FILE_NAMES)}）")

    # モジュールの作成 -------------------------------------------------------------

    new_kinds = _cppbuild.NEW_KINDS
    default_new_kind = "app"

    @classmethod
    def check_new(cls, name: str, kind: str | None, project: str | None = None, *, test: bool = True) -> None:
        _cppbuild.check_new_projects(name, kind or cls.default_new_kind, project, test=test)

    @classmethod
    def populate(cls, root: Path, config: ModuleConfig, kind: str | None, project: str | None = None, *,
                 test: bool = True) -> None:
        _cppbuild.create_module_solution(root, config.name, kind or cls.default_new_kind, project, test=test)
        _cppbuild.update(root)

    @classmethod
    def gitignore(cls) -> str:
        return GITIGNORE

    @classmethod
    def tracked_patterns(cls) -> tuple[str, ...]:
        return TRACKED_PATTERNS

    @classmethod
    def readme_usage(cls, config: ModuleConfig) -> str:
        return """## ビルド

CMake 3.24以上とC++20のコンパイラでビルドできます（依存先は構成時に取得されます）。

```sh
cmake -S .ecobuild/.cppbuild -B build
cmake --build build --config Debug
ctest --test-dir build -C Debug --output-on-failure
```
"""

    @classmethod
    def ci_workflow(cls, config: ModuleConfig) -> str:
        ci = config.ci
        runners = ci_workflow.runners(ci, ("windows", "linux"))
        configurations = ci_workflow.yaml_list(ci.configurations)
        libraries = "OFF, ON" if ci.shared else "OFF"
        on = "\n".join(ci_workflow.trigger(config))
        return f"""# ECOBuild（ecobuild ci init）が作成：ECOBuildなしで、CMakeだけで構成・ビルド・テストする。
# 変えるときは ecobuild ci init の --os・--configuration・--shared・--branches（設定は .ecobuild/ecobuild.toml の [ci]）。
name: build

{on}

jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        os: {runners}
        configuration: {configurations}
        shared: [{libraries}]     # ON：ライブラリを共有ライブラリにする（BUILD_SHARED_LIBS）
    runs-on: ${{{{ matrix.os }}}}
    steps:
      - uses: actions/checkout@v4
      - name: Configure
        run: cmake -S .ecobuild/.cppbuild -B build -DCMAKE_BUILD_TYPE=${{{{ matrix.configuration }}}} -DBUILD_SHARED_LIBS=${{{{ matrix.shared }}}}
        env:
          # 非公開の依存先を構成時にcloneするため。GITHUB_TOKEN はこのリポジトリしか読めないので、
          # 別の非公開リポジトリに依存するときは、それを読めるトークンを secrets.ECOBUILD_DEPS_TOKEN に登録する
          # （ecobuild ci secret set ECOBUILD_DEPS_TOKEN）。
          GIT_CONFIG_COUNT: 1
          GIT_CONFIG_KEY_0: url.https://x-access-token:${{{{ secrets.ECOBUILD_DEPS_TOKEN || secrets.GITHUB_TOKEN }}}}@github.com/.insteadOf
          GIT_CONFIG_VALUE_0: https://github.com/
      - name: Build
        run: cmake --build build --config ${{{{ matrix.configuration }}}}
      - name: Test
        run: ctest --test-dir build -C ${{{{ matrix.configuration }}}} --output-on-failure
"""

    @classmethod
    def tool_settings(cls) -> dict[str, str]:
        return {"cmake": "C++のビルドに使う cmake のパス（このPCだけ。既定は PATH の cmake）",
                "ctest": "C++のテストに使う ctest のパス（このPCだけ。既定は PATH の ctest）"}

    @classmethod
    def container_packages(cls) -> tuple[str, ...]:
        return ("cmake", "ninja-build", "g++")

    @classmethod
    def doctor_items(cls):
        from ecobuild.results import DoctorItem
        try:
            from cppbuild import Environment, EnvironmentOptions
            report = Environment.check(EnvironmentOptions(require_ctest=True))
        except Exception as error:  # CppBuildの診断そのものが失敗した
            return [DoctorItem("CMake・コンパイラ", False, True, f"{type(error).__name__}: {error}",
                              "CMake と C++ コンパイラをインストールしてください。", "install", _install("compiler"))]
        result = []
        for item in report.items:
            detail = " ".join(part for part in (item.version or "", item.path or "") if part) or item.detail
            result.append(DoctorItem(item.name, item.success, True, detail if item.success else (item.detail or detail),
                                    item.action or "CMake と C++ コンパイラ（Windows：Visual Studio のC++、"
                                                   "Linux：g++）が必要です。", "install",
                                    _install("cmake" if item.name in ("cmake", "ctest") else "compiler")))
        return result

    # 生成ファイルと、手元をそろえる処理 -----------------------------------------------

    def is_generated(self, path: str) -> bool:
        return _cppbuild.is_generated(path)

    def is_managed(self, path: str) -> bool:
        return _cppbuild.is_generated_or_managed(path)

    def refresh(self) -> bool:
        if not (self.root / _cppbuild.CONFIG_DIRECTORY).is_dir():
            return False
        self._update()
        return True

    def prepare(self) -> PrepareResult:
        if not (self.root / _cppbuild.CONFIG_DIRECTORY).is_dir():
            return PrepareResult((), False)
        changes = self._align_dependencies()
        self._update()
        return PrepareResult(changes, True)

    # ビルド ---------------------------------------------------------------------

    def validate_profile(self, profile: Profile) -> None:
        if profile.configuration not in _cppbuild.CONFIGURATIONS:
            raise EcoBuildError(ErrorCode.INVALID_CONFIGURATION, f"構成 {profile.configuration} はありません。",
                                hint=f"{'・'.join(_cppbuild.CONFIGURATIONS)} のどれかを指定してください。")
        if profile.parallel < 1:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "並列数は1以上にしてください。")
        _check_options(profile.options, PROFILE_OPTIONS, "ビルド設定")
        kinds = {p.name: p.kind for p in self.projects()} if profile.projects else {}
        for project, values in profile.projects.items():
            _check_options(values, PROFILE_PROJECT_OPTIONS, f"Project {project} の設定")
            if project not in kinds:
                raise EcoBuildError(ErrorCode.PROJECT_NOT_FOUND, f"Project {project} はありません。",
                                    hint=f"{self.module.op('profile project')} <名前> {project} --clear で外せます。")
            if "type" in values and not kinds[project].endswith("library"):
                raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{project} はライブラリではないので、形式を変えられません。")

    def build_options(self, profile: Profile | None, configuration: str) -> _cppbuild.BuildOptions:
        from ecobuild import settings
        selected = profile or Profile()
        _check_options(selected.options, PROFILE_OPTIONS, "ビルド設定")   # ecobuild.toml を手で直した場合
        for project, values in selected.projects.items():
            _check_options(values, PROFILE_PROJECT_OPTIONS, f"Project {project} の設定")
        tools = settings.load_config()
        return _cppbuild.BuildOptions(
            configuration or selected.configuration, selected.parallel, selected.shared,
            **selected.options, cmake=tools.get("cmake"), ctest=tools.get("ctest"), command=self.module.command,
            projects=tuple((name, _cppbuild.ProjectOptions(**values)) for name, values in selected.projects.items()))

    def build(self, project: str | None, options: _cppbuild.BuildOptions, action: str) -> BuildResult:
        outcome = _cppbuild.build(self.root, project=project, options=options, action=action)
        return BuildResult(project, options.configuration, tuple(Path(a).as_posix() for a in outcome.artifacts),
                           None, action)

    def test(self, project: str | None, options: _cppbuild.BuildOptions) -> TestResult:
        outcome = _cppbuild.test(self.root, project=project, options=options)
        cases = tuple(TestCaseResult(c.name, c.status) for c in outcome.cases)
        count = lambda status: sum(1 for c in cases if c.status == status)  # noqa: E731
        failed = len(cases) - count("passed") - count("skipped")
        return TestResult(project, options.configuration, count("passed"), failed, count("skipped"), cases)

    def run(self, project: str | None, options: _cppbuild.BuildOptions, arguments: str) -> RunResult:
        outcome = _cppbuild.run(self.root, project=project, options=options, arguments=arguments)
        last = outcome.processes[-1] if outcome.processes else None
        return RunResult(project, options.configuration, 0 if last is None else last.returncode,
                         "" if last is None else last.output)

    # Project ---------------------------------------------------------------------

    def project_at(self, path: Path) -> str | None:
        return _cppbuild.project_at(self.root, Path(path))

    def executable_at(self, path: Path) -> str | None:
        project = self.project_at(path)
        executables = {p.name for p in self.projects() if p.kind == "executable"}
        return project if project in executables else None

    def projects(self) -> tuple[ProjectSummary, ...]:
        return _cppbuild.list_projects(self.root)

    def add_project(self, name: str, kind: str, *, link: str | None = None, test: bool = True) -> FilesChanged:
        files = _cppbuild.add_project(self.root, name, kind, link=link, test=test)
        return FilesChanged("project add", files, name)

    def remove_project(self, name: str) -> FilesChanged:
        directory = _cppbuild.project_root(self.root, name)
        if _cppbuild.remove_project(self.root, name):
            self.module.repository.notices.append(
                f"{name} は、他のモジュールからリンクされるProject（最初に作ったProject）でした。"
                "このモジュールは、他のモジュールからリンクできなくなりました。")
        if directory.is_dir():
            remove_tree(directory)
        return FilesChanged("project remove", (directory.relative_to(self.root).as_posix(),), name)

    def set_pch(self, project: str, *, enable: bool = True) -> FilesChanged:
        """プリコンパイル済みヘッダー（include/<Project>/pch.h）を使う（enable=False：使わない）。"""
        self.module.require_task_branch("PCHの設定")
        header = _cppbuild.set_pch(self.root, project, enable=enable)
        return FilesChanged("pch" if enable else "pch off", (header,) if header else (), project)

    # 保存する設定 ---------------------------------------------------------------------

    def module_settings(self) -> dict:
        return _settings.module_settings(self.root)

    def set_module_settings(self, **changes) -> dict:
        return _settings.set_module_settings(self.root, **changes)

    def add_template(self, name: str, source: Path | str) -> dict:
        """ファイルテンプレートを登録する（file add --template で使う）。"""
        self.module.require_task_branch("テンプレートの登録")
        source = Path(source)
        return _settings.add_template(self.root, name, source)

    def remove_template(self, name: str) -> dict:
        self.module.require_task_branch("テンプレートの削除")
        return _settings.remove_template(self.root, name, command=self.module.command)

    def project_details(self, name: str) -> dict:
        return _settings.project_details(self.root, name)

    def set_project(self, name: str, **changes) -> dict:
        return _settings.set_project(self.root, name, **changes)

    def set_pch_headers(self, name: str, *, headers: tuple[str, ...] = (),
                        system_headers: tuple[str, ...] = ()) -> dict:
        """PCHに入れるヘッダー（Projectのヘッダーと、<> で読む標準・外部のヘッダー）。"""
        self.module.require_task_branch("PCHの設定")
        return _settings.set_pch(self.root, name, headers=headers, system_headers=system_headers)

    def move_project(self, name: str, destination: str) -> FilesChanged:
        return FilesChanged("project move", (_settings.move_project(self.root, name, destination, command=self.module.command),), name)

    def link_project(self, name: str, library: str, *, as_type: str | None) -> dict:
        return _settings.link_project(self.root, name, library, as_type)

    def link_package(self, name: str, package: str, *, target: str, directory: str) -> dict:
        """CMakeのパッケージ（find_package）をリンクする。"""
        self.module.require_task_branch("パッケージのリンク")
        return _settings.link_package(self.root, name, package, target, directory)

    def link_cmake(self, name: str, directory: str, *, target: str) -> dict:
        """CMakeのソース（add_subdirectory）をリンクする。"""
        self.module.require_task_branch("CMakeのソースのリンク")
        return _settings.link_cmake(self.root, name, directory, target)

    def link_library_file(self, name: str, *, kind: str = "static", locations: dict[str, str] | None = None,
                          import_libraries: dict[str, str] | None = None,
                          include_directories: tuple[str, ...] = ()) -> dict:
        """ビルド済みのライブラリ（構成 → パス）をリンクする。"""
        self.module.require_task_branch("ビルド済みのライブラリのリンク")
        return _settings.link_library_file(self.root, name, kind, locations or {}, import_libraries or {},
                                           include_directories)

    def unlink_project(self, name: str, link: str) -> dict:
        return _settings.unlink(self.root, name, link, command=self.module.command)

    # ファイル -------------------------------------------------------------------------

    def add_files(self, paths: list[Path], *, test: bool, template: str | None = None) -> list[FilesChanged]:
        """ヘッダーを先に作り、同じ名前のヘッダーを一緒に足したソースは、それを相対パスで読み込む
        （file add include/App/Foo.h src/Foo.cpp → #include "../include/App/Foo.h"）。"""
        headers = [p for p in paths if p.suffix.lower() in _cppbuild.HEADER_SUFFIXES]
        ordered = headers + [p for p in paths if p not in headers]
        changed = []
        for path in ordered:
            pair = None
            if path.suffix.lower() in _cppbuild.SOURCE_SUFFIXES:
                same = [h for h in headers if h.stem == path.stem]
                pair = next((h for h in same if h.parent == path.parent), same[0] if same else None)
            changed.append(self.add_file(path, test=test, template=template, pair_header=pair))
        return changed

    def add_file(self, path: Path, *, test: bool, template: str | None = None,
                 pair_header: Path | None = None) -> FilesChanged:
        """ライブラリの src/ のソースなら、テスト用Projectの同じ構成の場所にテストも足す（I-014）。
        template を指定すると、そのテンプレートから作る（テストは作らない）。pair_header：一緒に足したヘッダー
        （ソースはそれを相対パスで読み込む）。"""
        project, relative = self._in_project(path)
        self._require_source_directory(path, project, relative)
        header = self._header_for(project, relative)
        test_header = header
        if pair_header is not None:
            header, test_header = self._pair_includes(project, relative, pair_header)
        if template is not None:
            values = {"header": header or "", "suite": Path(relative).stem, "name": Path(relative).stem,
                      "project": project}
            return FilesChanged("file add", (_settings.add_file_from_template(self.root, project, relative, template,
                                                                              values, command=self.module.command),), project)
        added = [_cppbuild.add_file(self.root, project, relative, replacements={"header": header})]
        mirror = self._test_mirror(project, relative)
        if test and mirror is not None:
            test_project = _cppbuild.test_project_of(project)
            if test_header is None:   # ヘッダーが include/ の外：テストからも相対パスで
                test_header = Path(os.path.relpath(self._absolute(pair_header),
                                                   (_cppbuild.project_root(self.root, test_project) / mirror).parent)).as_posix()
            added.append(_cppbuild.add_file(self.root, test_project, mirror, template="unit_test",
                                            replacements={"header": test_header, "suite": Path(relative).stem}))
        return FilesChanged("file add", tuple(added), project)

    def _pair_includes(self, project: str, relative: str, pair_header: Path) -> tuple[str, str | None]:
        """一緒に足したヘッダーの読み込み方：ソースからは相対パス。テストからは、ヘッダーが include/ の中なら
        include/ からの相対（テストはライブラリの include/ を使える）、外なら None（テストの場所からの相対にする）。"""
        target = self._absolute(pair_header)
        root = _cppbuild.project_root(self.root, project).resolve()
        source = Path(os.path.relpath(target, (root / relative).parent)).as_posix()
        include = root / "include"
        return source, target.relative_to(include).as_posix() if target.is_relative_to(include) else None

    @staticmethod
    def _absolute(path: Path) -> Path:
        return (Path.cwd() / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()

    def remove_file(self, path: Path, *, test: bool) -> FilesChanged:
        project, relative = self._in_project(path)
        removed = [_cppbuild.remove_file(self.root, project, relative)]
        mirror = self._test_mirror(project, relative)
        test_project = _cppbuild.test_project_of(project)
        if test and mirror is not None and (_cppbuild.project_root(self.root, test_project) / mirror).is_file():
            removed.append(_cppbuild.remove_file(self.root, test_project, mirror))
        return FilesChanged("file remove", tuple(removed), project)

    def move_file(self, source: Path, destination: Path, *, test: bool) -> FilesChanged:
        project, relative = self._in_project(source)
        other, target = self._in_project(destination)
        if other != project:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "別のProjectへは移動できません。",
                                hint="移動先も同じProjectのディレクトリの中にしてください。")
        self._require_source_directory(destination, project, target)
        moved = list(_cppbuild.move_file(self.root, project, relative, target))
        mirror, mirror_target = self._test_mirror(project, relative), self._test_mirror(project, target)
        test_project = _cppbuild.test_project_of(project)
        if test and mirror and mirror_target and (_cppbuild.project_root(self.root, test_project) / mirror).is_file():
            moved += _cppbuild.move_file(self.root, test_project, mirror, mirror_target)
        return FilesChanged("file move", tuple(moved), project)

    def _in_project(self, path: Path) -> tuple[str, str]:
        """パス（今いるディレクトリからの相対か絶対）から、Projectとその中の相対パスを決める（I-027）。"""
        absolute = (Path.cwd() / Path(path)).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        project = _cppbuild.project_at(self.root, absolute)
        if project is None:
            raise EcoBuildError(ErrorCode.NOT_IN_PROJECT, f"{path} はどのProjectの中でもありません。",
                                hint=f"Projectのディレクトリの中のパスを指定してください（{self.module.op('project list')} で一覧）。")
        relative = absolute.relative_to(_cppbuild.project_root(self.root, project).resolve()).as_posix()
        return project, relative

    def _require_source_directory(self, path: Path, project: str, relative: str) -> None:
        """ソースフォルダー（src・include 等）の外には作らない・移さない。CppBuildはその外のファイルをビルドに入れず、
        Visual Studio でも「その他のファイル」になる。"""
        directories = _cppbuild.source_directories(self.root, project)
        if not any(Path(directory) in Path(relative).parents for directory in directories):
            names = "・".join(directories)
            raise EcoBuildError(ErrorCode.NOT_IN_SOURCE_DIRECTORY,
                                f"{path} はProject {project} のソースフォルダー（{names}）の外です。",
                                hint=f"{names} の中に置いてください（ソースフォルダーの外のファイルはビルドに入りません）。")

    def _header_for(self, project: str, relative: str) -> str | None:
        """ソースが読み込むヘッダー：include/ の同じ構成の場所にあればそれ、なければそのProjectのヘッダー
        （ライブラリ）、なければリンクしているライブラリのヘッダー。どれもなければ None（空のファイルにする）。"""
        path = Path(relative)
        root = _cppbuild.project_root(self.root, project)
        if path.parts[:1] == ("src",):
            candidate = Path("include", project, *path.parts[1:]).with_suffix(".h")
            if (root / candidate).is_file():
                return Path(project, *path.parts[1:]).with_suffix(".h").as_posix()
        if (root / "include" / _cppbuild.library_header(project)).is_file():
            return _cppbuild.library_header(project)
        for library in _cppbuild.linked_libraries(self.root, project):
            return _cppbuild.library_header(library)
        return None

    def _test_mirror(self, project: str, relative: str) -> str | None:
        """ライブラリの src/ のソースに対応する、組のテスト用Project（<ライブラリ>Test）のテストファイル
        （src/... /<名前>Test.cpp）。組のテスト用Projectがなければ None。"""
        path = Path(relative)
        if path.parts[:1] != ("src",) or path.suffix.lower() not in _cppbuild.SOURCE_SUFFIXES \
                or not self._has_test_project(project):
            return None
        return path.with_name(f"{path.stem}Test{path.suffix}").as_posix()

    def _has_test_project(self, library: str) -> bool:
        names = {p.name for p in self.projects()}
        return library in names and _cppbuild.test_project_of(library) in names \
            and _cppbuild.is_test_project(self.root, _cppbuild.test_project_of(library))

    # 生成ファイルの更新（変わっていなければ飛ばす） ---------------------------------------

    def _selected_options(self) -> _cppbuild.BuildOptions | None:
        """このPCで選んだビルド設定（生成器等。構成の作り直しを、ビルドと同じビルドツリーで行うため）。読めなければNone。"""
        try:
            return self.module.build_options()[0]
        except EcoBuildError:
            return None

    def _update(self) -> None:
        """CppBuildの update（構成と生成ファイルの作り直し。約1秒）を、入力が前回から変わったときだけ行う。

        入力：管理ファイル・生成ファイルの中身、依存先の同じもの、CppBuildの版。ソースの追加・削除は
        含まない（生成ファイルに一覧はなく、CMakeがビルドのたびに集める）。記録は build/ に置く（git の管理外。消えれば必ず行う）。
        """
        stamp = self.root / _cppbuild.BUILD_DIRECTORY / ".ecobuild-update"
        try:
            if stamp.is_file() and stamp.read_text(encoding="utf-8") == _fingerprint(self.root):
                return
        except OSError:
            pass
        _cppbuild.update(self.root, self._selected_options())
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(_fingerprint(self.root), encoding="utf-8")  # 作り直した後の生成ファイルで記録する

    # 依存先 ------------------------------------------------------------------------

    def link(self, url: str, *, project: str | None, shared: bool) -> LinkResult:
        """project を省くと、テスト用を除いてProjectが1つならそれ。"""
        target = project or self._only_project()
        name = _cppbuild.link(self.root, target, url, shared=shared)
        revision = next(s.revision for s in _cppbuild.git_sources(self.root) if s.name == name)
        # 依存先の依存先として既にcloneがあると、CppBuildは記録だけ進める。手元も記録の版に合わせる（作業版は触らない）。
        clone = next((c for c in self._align_dependencies() if c.name == name), None)
        if clone is not None and clone.action == "aligned":
            self._update()
        return LinkResult(name, url, revision, (target,), clone=clone)

    def _only_project(self) -> str:
        """テスト用を除いて、Projectが1つならそれ（ライブラリと組のテスト用だけなら、ライブラリ）。"""
        names = [p.name for p in self.projects() if p.kind != "test"]
        if len(names) != 1:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "リンクするProjectを決められません。",
                                hint=f"--project で指定するか、Projectのディレクトリの中で実行してください"
                                     f"（Project：{'、'.join(names) or 'なし'}）。")
        return names[0]

    def unlink(self, name: str) -> LinkResult:
        """手元のcloneは、記録の版のままなら消す（作業中・変更ありなら残す）。"""
        source = self._source(name)
        projects = _cppbuild.unlink(self.root, name)
        directory = Path(source.directory)
        removable = directory.is_dir() and self._dependency_state(source).state == "aligned"
        if removable:
            remove_tree(directory)
        return LinkResult(name, source.url, source.revision, projects, removable)

    def dependencies(self) -> tuple[DependencyState, ...]:
        return tuple(self._dependency_state(s) for s in _cppbuild.git_sources(self.root))

    def all_dependencies(self) -> tuple[DependencyState, ...]:
        return tuple(replace(self._dependency_state(s), via=via) for s, via in _cppbuild.all_git_sources(self.root))

    def dependency_tree(self) -> DependencyTree:
        sources, edges = _cppbuild.dependency_graph(self.root)
        nodes = tuple(DependencyNode(s.name, s.url, s.revision, s.present, edges[s.name]) for s in sources)
        return DependencyTree(self.module.name, tuple(s.name for s in sources if s.recorded_by is None), nodes)

    def update_dependencies(self, name: str | None) -> tuple[DependencyChange, ...]:
        """依存先の記録を、GitHubの最新にする（I-018）。手元のcloneも合わせ、生成ファイルを更新する。"""
        names = [name] if name else [s.name for s in _cppbuild.git_sources(self.root)]
        if name:
            self._source(name)
        updated = {}
        for each in names:
            before = self._source(each).revision
            updated[each] = (before, _cppbuild.record_latest(self.root, each))
        changes = []
        for change in self._align_dependencies():
            if change.name not in updated:
                continue
            before, after = updated[change.name]
            note = "最新です" if before == after else f"{before[:7]} → {after[:7]}"
            changes.append(DependencyChange(change.name, change.action,
                                            note if change.reason is None else f"{note}（{change.reason}）"))
        self._update()
        return tuple(changes)

    def sync_dependencies(self) -> tuple[DependencyChange, ...]:
        changes = self._align_dependencies()
        self._update()
        return changes

    def _align_dependencies(self) -> tuple[DependencyChange, ...]:
        """依存先を記録の版に合わせる。作業版（task/のブランチ）・手元で変更やコミットのあるものは触らない。"""
        fetched, sources = _cppbuild.fetch_dependencies(self.root)
        changes = []
        for source in sources:
            if source.name in fetched:
                changes.append(DependencyChange(source.name, "cloned"))
                continue
            clone = Git(source.directory, command=self.module.command)
            head = clone.rev_parse("HEAD")
            branch = clone.current_branch()
            if branch is not None and wm.is_task_branch(branch):
                # 依存先の中で task start をした作業版（I-019）。記録の版へ切り替えない。
                changes.append(DependencyChange(source.name, "skipped", f"作業版です（{branch}）"))
                continue
            if head == source.revision and branch is None:
                changes.append(DependencyChange(source.name, "unchanged"))
                continue
            if not clone.working_tree().clean:
                changes.append(DependencyChange(source.name, "skipped", "未コミットの変更があります"))
                continue
            clone.fetch()
            if not clone.output("branch", "--remotes", "--contains", head):
                changes.append(DependencyChange(source.name, "skipped", "GitHubにないコミットがあります"))
                continue
            clone.run("switch", "--quiet", "--detach", source.revision)
            changes.append(DependencyChange(source.name, "aligned"))
        return tuple(changes)

    def _source(self, name: str):
        source = next((s for s in _cppbuild.git_sources(self.root) if s.name == name), None)
        if source is None:
            names = [s.name for s in _cppbuild.git_sources(self.root)]
            raise EcoBuildError(ErrorCode.DEPENDENCY_NOT_FOUND, f"依存先 {name} はありません。",
                                hint=f"依存先：{'、'.join(names) or 'なし'}（{self.module.op('deps list')}）")
        return source

    def _dependency_state(self, source) -> DependencyState:
        directory = Path(source.directory)
        if not (directory / ".git").exists():
            return DependencyState(source.name, source.url, source.revision, None, "missing")
        clone = Git(directory, command=self.module.command)
        head = clone.rev_parse("HEAD")
        branch = clone.current_branch()
        if branch is not None and wm.is_task_branch(branch):
            state = "working"
        elif not clone.working_tree().clean:
            state = "modified"
        else:
            state = "aligned" if head == source.revision else "differs"
        return DependencyState(source.name, source.url, source.revision, head, state, branch)
