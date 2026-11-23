"""型 cpp：Project・ファイル・ビルド・テスト・依存先を、CppBuildで扱う。

本体の型の口（ModuleType と能力）を実装する。C++だけの操作（PCH・ファイルテンプレート・CMakeのパッケージ／ソース・
ビルド済みファイルのリンク）は型の口にないので、この型の公開メソッドとして出す（ecobuild_cpp.cpp(module) から使う）。
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
from dataclasses import replace
from importlib import metadata
from pathlib import Path

from ecowork import model as wm
from ecowork.git import Git

from ecobuild import ci_workflow
from ecobuild.config import ModuleConfig, Profile
from ecobuild.errors import EcoBuildError

from .errors import ErrorCode
from ecobuild.fsutil import remove_tree
from ecobuild.module_type import Builds, HasDependencies, HasFiles, HasProjects, ModuleType
from ecobuild.results import (BuildResult, DependencyChange, DependencyCommit, DependencyLibraries, DependencyLibrary,
                              DependencyLink, DependencyNode, DependencyState,
                              DependencyTag, DependencyTree, DependencyVersions, DependencyWorkResult, DependencyWorkSource, FilesChanged, LinkResult, PrepareResult, ProjectSummary, RunResult, TestCaseResult,
                              TestEntry, TestResult)

from . import _cppbuild, _migrate, _revisions, _settings, _work

_INCLUDE = re.compile(r'^([ \t]*#[ \t]*include[ \t]*)"([^"\r\n]+)"', re.MULTILINE)   # #include "…"（<…> は直さない）


# 名前付きビルド設定の、型 cpp の項目（[profiles.<名前>] の configuration・shared・parallel 以外）：
# 名前 → (値の型, 使える値。None は何でも)。値の意味は _cppbuild.BuildOptions
_POSITIVE = range(1, 1 << 16)
SEP = "\x1f"   # git の --format の欄の区切り（件名に出てこない）


def _fields(text: str, count: int) -> list[tuple[str, ...]]:
    """SEP で区切った行の欄（count 個。後ろの欄に SEP が出てきてもそこで切らない）。"""
    return [tuple(line.split(SEP, count - 1)) for line in text.splitlines() if line]

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

# CppBuildの中間ファイル・成果物・作業中のロック
/.ecobuild/.cppbuild/output/
/.ecobuild/.cppbuild/operations/
"""

# 改行はLFにそろえる（Windows の core.autocrlf=true で CRLF にされると、コンテナ〔Linux〕の git から全ファイルが変更ありに
# 見え、依存先として clone したときも同じ）。型の .gitattributes（type の gitattributes）。本体が新しいモジュールに置き、
# module upgrade・adopt では足りない行を足す（* の行は先頭に足すので、元のリポジトリの *.ps1 等の決まりを上書きしない）
GITATTRIBUTES = """\
* text=auto eol=lf
*.ps1 text eol=crlf
*.cmd text eol=crlf
*.bat text eol=crlf
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
    def adopt(cls, root: Path, config: ModuleConfig) -> None:
        """Project のない Solution だけを作る（今あるソースは Project に入れない。project add で足す）。"""
        if not (root / _cppbuild.CONFIG_DIRECTORY).exists():
            _cppbuild.create_module_solution(root, config.name, "none")
            _cppbuild.update(root)

    @classmethod
    def gitignore(cls) -> str:
        return GITIGNORE

    @classmethod
    def gitattributes(cls) -> str:
        return GITATTRIBUTES

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
    def apt_packages(cls) -> tuple[str, ...]:
        return ("cmake", "ninja-build", "g++")

    @classmethod
    def build_outputs(cls) -> tuple[str, ...]:
        return ("build",)   # CMake の構成・出力・取ってきた依存（FetchContent）

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

    def upgrade(self) -> None:
        """CppBuild の管理ファイルが古い形式なら今の形式にしてから（_migrate）、生成ファイルを作り直す。

        移したのに作り直せなければ（依存先がまだ古い形式の版・CMake の構成の失敗等）、タスクブランチでは止めずに案内を残す：
        移した分はコミットさせる（このモジュールの形式が新しくないと deps update 等ができない。生成ファイルは次の操作・提出の前に
        作り直される）。タスクブランチでなければ（push まで行くので）止める（module upgrade が書いたものを戻す）。"""
        config = self.root / _cppbuild.CONFIG_DIRECTORY
        if _migrate.needs_cleanup(config):   # 前に移したときに片付けられなかった古い置き場所
            _migrate.cleanup(config)
        if not _migrate.is_old(config):
            self.refresh()
            return
        _migrate.convert(config)
        try:
            self.refresh()
        except EcoBuildError as error:
            if self.module.repository.current_task_branch() is None:
                raise
            self.module.repository.notices.append(
                f"CppBuild の管理ファイルを新しい形式にしましたが、生成ファイルは作り直せませんでした：{error.message}"
                + (f"\n{error.hint}" if error.hint else ""))
        if _migrate.needs_cleanup(config):
            self.module.repository.notices.append(
                f"{_cppbuild.CONFIG_DIRECTORY}/{_migrate.OLD_SUBPROJECTS}/ を消せませんでした（Visual Studio 等が使っていないか"
                f"確かめてください）。もう一度 {self.module.op('module upgrade')} をすると片付けます。")

    def upgrade_paths(self) -> tuple[str, ...]:
        """古い形式なら、移す管理ファイル（移す元と先）。"""
        config = self.root / _cppbuild.CONFIG_DIRECTORY
        if not _migrate.is_old(config):
            return ()
        _, moves = _migrate.plan(config)
        return tuple(sorted({f"{_cppbuild.CONFIG_DIRECTORY}/{path}" for move in moves for path in move if path}))

    def rename(self, previous: str, *, dry_run: bool = False) -> tuple[str, ...]:
        """Solution の名前（CMake の project()・.sln）がモジュール名と同じなら、新しい名前にする。main の Project の名前・
        include/<名前>/・<名前>Test は変えない（依存元の #include・リンクが使う）。"""
        if not (self.root / _cppbuild.CONFIG_DIRECTORY).is_dir() or _settings.solution_name(self.root) != previous:
            return ()
        if not dry_run:
            _settings.set_solution_name(self.root, self.module.name)   # 生成ファイルも作り直す（CppBuild の構成まで）
        return (f"{_cppbuild.CONFIG_DIRECTORY}/solution.json",)

    def relocated(self) -> tuple[str, ...]:
        """CMake のビルドツリー（build/。CMakeCache に前の場所が入っている）を消す。依存先の clone（deps/）はそのまま使える。"""
        build = self.root / _cppbuild.BUILD_DIRECTORY
        if not build.is_dir():
            return ()
        remove_tree(build)
        return (_cppbuild.BUILD_DIRECTORY,)

    def update_solution(self) -> dict:
        """構成（Visual Studio のソリューション・プロジェクト等）を今のファイルに合わせる。ビルドはしない。file add 等と
        同じビルドツリーで、ファイルが変わっていなければ CMake は動かない（約0.1秒）。コンテナの中やエディターで足した・
        移したファイルを、このPCの Visual Studio に見せるのに使う。configured：作り直したか。"""
        outcome = _cppbuild.update(self.root)
        return {"configured": any(not p.output.startswith("CMake was not run") for p in outcome.processes)}

    def prepare(self) -> PrepareResult:
        if not (self.root / _cppbuild.CONFIG_DIRECTORY).is_dir():
            return PrepareResult((), False)
        if _migrate.is_old(self.root / _cppbuild.CONFIG_DIRECTORY):
            # 古い形式：作業を始める・取り込むこと（その後の module upgrade のため）は止めず、案内だけ残す
            self.module.repository.notices.append(
                f"CppBuild の管理ファイルが古い形式です。{self.module.op('module upgrade')} で新しい形式にしてください"
                "（それまで依存先・生成ファイルはそろえません）。")
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

    @staticmethod
    def program_output(write, *, tools: bool = True):
        """この中の build・test・run 等で動かすツール・プログラムの出力を、1行ずつ write(行, stream, source) に渡す
        （with で使う。結果・誤りの output は今までどおり全部入る）。tools：ツールの出力も（偽なら実行するプログラムだけ）。"""
        return _cppbuild.program_output(write, tools=tools)

    def build(self, project: str | None, options: _cppbuild.BuildOptions, action: str) -> BuildResult:
        outcome = _cppbuild.build(self.root, project=project, options=options, action=action)
        return BuildResult(project, options.configuration, tuple(Path(a).as_posix() for a in outcome.artifacts),
                           None, action)

    def test(self, project: str | None, options: _cppbuild.BuildOptions, tests: tuple[str, ...] = ()) -> TestResult:
        """tests：<テスト用Project> か <テスト用Project>.<Suite>.<Test>（* ? が使える。_cppbuild.test）。"""
        outcome = _cppbuild.test(self.root, project=project, options=options, tests=tuple(tests))
        cases = tuple(TestCaseResult(c.name, c.status) for c in outcome.cases)
        count = lambda status: sum(1 for c in cases if c.status == status)  # noqa: E731
        failed = len(cases) - count("passed") - count("skipped")
        return TestResult(project, options.configuration, count("passed"), failed, count("skipped"), cases)

    def list_tests(self, project: str | None, options: _cppbuild.BuildOptions) -> tuple[TestEntry, ...]:
        """テスト用Projectのソースの TEST(…) 等から（ビルドしない。_cppbuild.list_tests）。"""
        return tuple(TestEntry(*found) for found in _cppbuild.list_tests(self.root, project=project))

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

    def set_project(self, name: str, *, kind: str | None = None, test: bool = True, **changes) -> dict:
        """kind：種類を変える（app・library・shared。ほかの設定はその後で変える）。test：ライブラリにするとき、
        組のテスト用Projectを作る（project add と同じく既定は作る）。足したファイルは created に入る。"""
        created: tuple[str, ...] = ()
        if kind is not None:
            if kind not in _cppbuild.LIBRARY_KINDS:   # ビルド設定の形式（type）はライブラリだけ
                using = sorted(n for n, p in self.module.config.profiles.items() if "type" in p.projects.get(name, {}))
                if using:
                    raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                                        f"ビルド設定 {'、'.join(using)} が {name} の形式（type）を変えているので、実行ファイルにできません。",
                                        hint=f"先に {self.module.op('profile project')} <名前> {name} --clear で外してください。")
            created = _cppbuild.change_kind(self.root, name, kind, test=test, command=self.module.command)
        unset = [key for key, value in changes.items()   # CLI は変えない項目も空で渡す（on／off は None）
                 if value is None or value == () or (value is False and key in ("clear_folder", "default_warning_level"))]
        if kind is None or len(unset) < len(changes):
            details = _settings.set_project(self.root, name, **changes)
        else:   # 種類だけ
            details = _settings.project_details(self.root, name)
        return {**details, "created": list(created)} if kind is not None else details

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
        before = self.module.own_changes()
        result = _settings.link_package(self.root, name, package, target, directory)
        self.module.commit_own_changes(f"{name} に {package}（{target}）をリンク", before)
        return result

    def link_cmake(self, name: str, directory: str, *, target: str) -> dict:
        """CMakeのソース（add_subdirectory）をリンクする。"""
        self.module.require_task_branch("CMakeのソースのリンク")
        before = self.module.own_changes()
        result = _settings.link_cmake(self.root, name, directory, target)
        self.module.commit_own_changes(f"{name} に {directory}（{target}）をリンク", before)
        return result

    def link_library_file(self, name: str, *, kind: str = "static", locations: dict[str, str] | None = None,
                          import_libraries: dict[str, str] | None = None,
                          include_directories: tuple[str, ...] = ()) -> dict:
        """ビルド済みのライブラリ（構成 → パス）をリンクする。"""
        self.module.require_task_branch("ビルド済みのライブラリのリンク")
        before = self.module.own_changes()
        result = _settings.link_library_file(self.root, name, kind, locations or {}, import_libraries or {},
                                             include_directories)
        self.module.commit_own_changes(f"{name} にビルド済みのライブラリをリンク", before)
        return result

    def unlink_project(self, name: str, link: str) -> dict:
        return _settings.unlink(self.root, name, link, command=self.module.command)

    # ファイル -------------------------------------------------------------------------

    def add_files(self, paths: list[Path], *, test: bool, template: str | None = None) -> list[FilesChanged]:
        """ヘッダーを先に作り、同じ名前のヘッダーを一緒に足したソースは、それを相対パスで読み込む
        （file add include/App/Foo.h src/Foo.cpp → #include "../include/App/Foo.h"）。"""
        headers = [p for p in paths if p.suffix.lower() in _cppbuild.HEADER_SUFFIXES]
        ordered = headers + [p for p in paths if p not in headers]
        sources = {p.stem for p in paths if p.suffix.lower() in _cppbuild.SOURCE_SUFFIXES}
        changed = []
        with _cppbuild.one_update(self.root):   # 構成の作り直しは最後に1回
            for path in ordered:
                pair = None
                if path.suffix.lower() in _cppbuild.SOURCE_SUFFIXES:
                    same = [h for h in headers if h.stem == path.stem]
                    pair = next((h for h in same if h.parent == path.parent), same[0] if same else None)
                # ヘッダーのテストは、同じ名前のソースを一緒に足すならそちら（テストは1つ）
                changed.append(self.add_file(path, test=test and not (path in headers and path.stem in sources),
                                             template=template, pair_header=pair))
        return changed

    def add_file(self, path: Path, *, test: bool, template: str | None = None,
                 pair_header: Path | None = None) -> FilesChanged:
        """ライブラリのヘッダー・src/ のソースなら、テスト用Projectの同じ構成の場所にテストも足す（I-014。ヘッダーの
        テストはそれを読み込む）。同じ場所のテストが既にあれば（同じ名前のヘッダー・ソースを先に足した）作らない。
        template を指定すると、そのテンプレートから作る（テストは作らない）。pair_header：一緒に足したヘッダー
        （ソースはそれを相対パスで読み込む）。"""
        with _cppbuild.one_update(self.root):   # ファイルとそのテストを足しても、構成の作り直しは1回
            return self._add_file(path, test=test, template=template, pair_header=pair_header)

    def _add_file(self, path: Path, *, test: bool, template: str | None, pair_header: Path | None) -> FilesChanged:
        project, relative = self._in_project(path)
        self._require_source_directory(path, project, relative)
        header = self._header_for(project, relative)
        test_header = header
        if pair_header is None:
            pair_header = self._header_beside(project, relative)
        if pair_header is not None:
            header, test_header = self._pair_includes(project, relative, pair_header)
        if template is not None:
            values = {"header": header or "", "suite": Path(relative).stem, "name": Path(relative).stem,
                      "project": project}
            return FilesChanged("file add", (_settings.add_file_from_template(self.root, project, relative, template,
                                                                              values, command=self.module.command),), project)
        added = [_cppbuild.add_file(self.root, project, relative, replacements={"header": header})]
        if Path(relative).suffix.lower() in _cppbuild.HEADER_SUFFIXES:
            location = self._test_of(project, relative)
            if test and location is not None and self._has_test_project(project)                     and not (_cppbuild.project_root(self.root, _cppbuild.test_project_of(project)) / location).exists():
                added += self.add_test(path).paths
            return FilesChanged("file add", tuple(added), project)
        mirror = self._test_mirror(project, relative)
        if mirror is not None and (_cppbuild.project_root(self.root, _cppbuild.test_project_of(project)) / mirror).exists():
            mirror = None   # 同じ名前のヘッダーを先に足したときのテスト
        if test and mirror is not None:
            test_project = _cppbuild.test_project_of(project)
            if test_header is None:   # ヘッダーが include/ の外：テストからも相対パスで
                test_header = Path(os.path.relpath(self._absolute(pair_header),
                                                   (_cppbuild.project_root(self.root, test_project) / mirror).parent)).as_posix()
            added.append(_cppbuild.add_file(self.root, test_project, mirror, template="unit_test",
                                            replacements={"header": test_header, "suite": Path(relative).stem}))
        return FilesChanged("file add", tuple(added), project)

    def add_test(self, path: Path, destination: Path | None = None, *, dry_run: bool = False) -> FilesChanged:
        """ライブラリのヘッダー・ソースのテストを作る。既定の場所は組のテスト用Project（<ライブラリ>Test）の src/ の、
        同じ構成の場所（include/<Project>/a/B.h・src/a/B.cpp → src/a/BTest.cpp）。テストはそのヘッダーを読み込む。"""
        project, relative = self._in_project(path)
        rel = Path(relative)
        suffix = rel.suffix.lower()
        if suffix not in _cppbuild.HEADER_SUFFIXES and suffix not in _cppbuild.SOURCE_SUFFIXES:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{path} はヘッダーでもソースでもありません。",
                                hint="テストを作れるのは、ライブラリのヘッダー・ソースです。")
        if not (_cppbuild.project_root(self.root, project) / rel).is_file():
            raise EcoBuildError(ErrorCode.FILE_NOT_FOUND, f"{path} がありません。")
        test_project = _cppbuild.test_project_of(project)
        if not self._has_test_project(project):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"Project {project} には組のテスト用Project（{test_project}）がありません。",
                                hint=f"テストを作れるのは、組のテスト用Projectがあるライブラリのファイルです"
                                     f"（{self.module.op('project list')} で確かめる）。")
        parts = rel.parts
        inner = Path(*parts[2:]) if parts[:2] == ("include", project) and len(parts) > 2 \
            else Path(*parts[1:]) if parts[:1] in (("src",), ("include",)) and len(parts) > 1 else Path(rel.name)
        if destination is None:
            target_project, target = test_project, Path("src", inner).with_name(f"{inner.stem}Test.cpp").as_posix()
        else:
            target_project, target = self._in_project(destination)
            self._require_source_directory(destination, target_project, target)
        target_root = _cppbuild.project_root(self.root, target_project)
        shown = (target_root / target).relative_to(self.root).as_posix()
        if dry_run:   # 場所だけ（既にあるかは、作るときに確かめる）
            return FilesChanged("file test", (shown,), target_project)
        if (target_root / target).exists():
            raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{shown} は既に存在します。")
        header = rel if suffix in _cppbuild.HEADER_SUFFIXES else None
        if header is None:
            beside = self._header_beside(project, relative)
            public = Path("include", project, inner).with_suffix(".h")
            header = (beside.resolve().relative_to(_cppbuild.project_root(self.root, project).resolve()) if beside
                      else public if (_cppbuild.project_root(self.root, project) / public).is_file() else None)
        include = ""
        if header is not None:
            absolute = (_cppbuild.project_root(self.root, project) / header).resolve()
            include_dir = (_cppbuild.project_root(self.root, project) / "include").resolve()
            if target_project == test_project and absolute.is_relative_to(include_dir):
                include = absolute.relative_to(include_dir).as_posix()   # テストはライブラリの include/ を使える
            else:
                include = Path(os.path.relpath(absolute, (target_root / target).parent.resolve())).as_posix()
        else:
            include = self._header_for(project, relative) or ""
        added = _cppbuild.add_file(self.root, target_project, target, template="unit_test" if include else None,
                                   replacements={"header": include, "suite": inner.stem} if include else None)
        return FilesChanged("file test", (added,), target_project)

    def _pair_includes(self, project: str, relative: str, pair_header: Path) -> tuple[str, str | None]:
        """一緒に足したヘッダーの読み込み方：ソースからは相対パス。テストからは、ヘッダーが include/ の中なら
        include/ からの相対（テストはライブラリの include/ を使える）、外なら None（テストの場所からの相対にする）。"""
        target = self._absolute(pair_header)
        root = _cppbuild.project_root(self.root, project).resolve()
        source = Path(os.path.relpath(target, (root / relative).parent)).as_posix()
        include = root / "include"
        return source, target.relative_to(include).as_posix() if target.is_relative_to(include) else None

    def _header_beside(self, project: str, relative: str) -> Path | None:
        """ソースと同じフォルダーにある同じ名前のヘッダー（実装用のヘッダーは .cpp と並べる）。"""
        path = Path(relative)
        if path.suffix.lower() not in _cppbuild.SOURCE_SUFFIXES:
            return None
        root = _cppbuild.project_root(self.root, project)
        return next((root / path.with_suffix(suffix) for suffix in _cppbuild.HEADER_SUFFIXES
                     if (root / path.with_suffix(suffix)).is_file()), None)

    @staticmethod
    def _absolute(path: Path) -> Path:
        return (Path.cwd() / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()

    def remove_file(self, path: Path, *, test: bool) -> FilesChanged:
        """ファイルかフォルダー（中身ごと）を削除する。ライブラリのヘッダー・ソースのテストも、ほかに対応する
        ファイルが残らなければ削除する（ヘッダーとソースの組は、両方を消したときにテストを消す）。"""
        project, relative = self._in_project(path)
        if Path(relative) == Path("."):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{path} はProjectのフォルダーそのものです。",
                                hint=f"Projectの削除は {self.module.op('project remove')} です。")
        files = self._files_in(project, relative)
        removals = [(project, f) for f in files]
        test_project = _cppbuild.test_project_of(project)
        if test and self._has_test_project(project):
            gone = set(files)
            staying = [f for f in self._library_files(project) if f not in gone]
            kept = {self._test_of(project, f) for f in staying}
            tests = dict.fromkeys(t for f in files for t in [self._test_of(project, f)] if t and t not in kept)
            removals += [(test_project, t) for t in tests if (_cppbuild.project_root(self.root, test_project) / t).is_file()]
        removed = _cppbuild.remove_files(self.root, removals)
        self._remove_empty_folders(project, relative)
        return FilesChanged("file remove", removed, project)

    def move_file(self, source: Path, destination: Path, *, test: bool) -> FilesChanged:
        """ファイルかフォルダー（中身ごと）を移動する。ライブラリのヘッダー・ソースのテストも同じ構成の場所へ移し
        （フォルダーなら、テスト用Projectの同じ構成のフォルダーごと）、移したファイルを読み込む #include を直す。"""
        project, relative = self._in_project(source)
        other, target = self._in_project(destination)
        if other != project:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "別のProjectへは移動できません。",
                                hint="移動先も同じProjectのディレクトリの中にしてください。")
        self._require_source_directory(destination, project, target)
        root = _cppbuild.project_root(self.root, project)
        folder = (root / relative).is_dir()
        if folder and (Path(target) == Path(relative) or Path(relative) in Path(target).parents):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "フォルダーをその中へは移せません。")
        if folder and (root / target).exists():
            raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{destination} は既に存在します。")
        if folder and not self._files_in(project, relative):   # 空のフォルダー：名前を変えるだけ
            (root / target).parent.mkdir(parents=True, exist_ok=True)
            (root / relative).rename(root / target)
            return FilesChanged("file move", (), project)
        pairs = {f: (Path(target) / Path(f).relative_to(relative)).as_posix() for f in self._files_in(project, relative)} \
            if folder else {relative: target}
        moves = [(project, old, new) for old, new in pairs.items()]
        if test and self._has_test_project(project):
            moves += self._test_moves(project, relative, target, pairs, folder)
        moved = _cppbuild.move_files(self.root, moves)
        if folder:
            self._remove_empty_folders(project, relative)
        edited = self._fix_includes({(_cppbuild.project_root(self.root, p) / old).resolve():
                                     (_cppbuild.project_root(self.root, p) / new).resolve() for p, old, new in moves})
        return FilesChanged("file move", moved, project, edited=tuple(edited))

    def _test_moves(self, project: str, relative: str, target: str, pairs: dict[str, str],
                    folder: bool) -> list[tuple[str, str, str]]:
        """移すライブラリのファイルに合わせて移す、組のテスト用Projectのファイル（Project, 元, 先）。
        フォルダー：テスト用Projectの同じ構成のフォルダーの中身ごと。ファイル：対応するテスト（移動先にまだないとき）。"""
        test_project = _cppbuild.test_project_of(project)
        test_root = _cppbuild.project_root(self.root, test_project)
        moves = {}
        if folder:
            old, new = self._test_folder_of(project, relative), self._test_folder_of(project, target)
            if old and new and (test_root / old).is_dir():
                moves = {f: (Path(new) / Path(f).relative_to(old)).as_posix() for f in self._files_in(test_project, old)}
        for source, destination in pairs.items():
            for old, new in zip(self._tests_of(project, source), self._tests_of(project, destination)):
                if old not in moves and (test_root / old).is_file() and not (test_root / new).exists() \
                        and new not in moves.values():
                    moves[old] = new
        return [(test_project, old, new) for old, new in moves.items()]

    def _inner(self, project: str, relative: str) -> Path | None:
        """ライブラリのファイル・フォルダーの、テスト用Projectでの構成（include/<Project>/… と src/… の … の部分）。"""
        parts = Path(relative).parts
        if parts[:2] == ("include", project):
            return Path(*parts[2:]) if len(parts) > 2 else None
        if parts[:1] in (("src",), ("include",)):
            return Path(*parts[1:]) if len(parts) > 1 else None
        return None

    def _test_of(self, project: str, relative: str) -> str | None:
        """ライブラリのヘッダー・ソースのテスト（file test の既定の場所：テスト用Projectの src/…/<名前>Test.cpp）。"""
        inner = self._inner(project, relative)
        if inner is None or Path(relative).suffix.lower() not in (*_cppbuild.HEADER_SUFFIXES, *_cppbuild.SOURCE_SUFFIXES):
            return None
        return Path("src", inner).with_name(f"{inner.stem}Test.cpp").as_posix()

    def _tests_of(self, project: str, relative: str) -> list[str]:
        """対応するテストの候補（file add が作る場所と、file test の既定の場所。拡張子が違うときだけ2つ）。"""
        found = [self._test_mirror(project, relative), self._test_of(project, relative)]
        return list(dict.fromkeys(t for t in found if t))

    def _test_folder_of(self, project: str, relative: str) -> str | None:
        inner = self._inner(project, relative)
        return Path("src", inner).as_posix() if inner is not None else None

    def _files_in(self, project: str, relative: str) -> list[str]:
        """ファイルならそれ、フォルダーなら中のファイルすべて（Projectからの相対）。"""
        root = _cppbuild.project_root(self.root, project)
        if not (root / relative).is_dir():
            return [Path(relative).as_posix()]
        return sorted(p.relative_to(root).as_posix() for p in (root / relative).rglob("*") if p.is_file())

    def _library_files(self, project: str) -> list[str]:
        """Projectのソースフォルダーの中のヘッダー・ソース（Projectからの相対）。"""
        root = _cppbuild.project_root(self.root, project)
        suffixes = (*_cppbuild.HEADER_SUFFIXES, *_cppbuild.SOURCE_SUFFIXES)
        return [p.relative_to(root).as_posix() for directory in _cppbuild.source_directories(self.root, project)
                if (root / directory).is_dir() for p in (root / directory).rglob("*")
                if p.is_file() and p.suffix.lower() in suffixes]

    def _remove_empty_folders(self, project: str, relative: str) -> None:
        """移動・削除で空になったフォルダー（と、テスト用Projectの同じ構成のフォルダー）を消す。ソースフォルダーは残す。"""
        places = [(project, relative)]
        if self._has_test_project(project) and self._test_folder_of(project, relative):
            places.append((_cppbuild.test_project_of(project), self._test_folder_of(project, relative)))
        for name, place in places:
            root = _cppbuild.project_root(self.root, name)
            keep = {(root / d).resolve() for d in _cppbuild.source_directories(self.root, name)} | {root.resolve()}
            folder = (root / place) if (root / place).is_dir() else (root / place).parent
            while folder.is_dir() and folder.resolve() not in keep and not any(folder.iterdir()):
                folder.rmdir()
                folder = folder.parent

    def _fix_includes(self, moved: dict[Path, Path]) -> list[str]:
        """移したファイルを読み込む・移したファイルが読み込む #include "…" を、新しい場所に直す。直したファイル
        （モジュールからの相対）を返す。読み込み先は、そのファイルの場所からの相対か、Projectの include/ からの相対。"""
        if not moved:
            return []
        names = [p.name for p in self.projects()]
        roots = [_cppbuild.project_root(self.root, n) for n in names]
        include_dirs = [(r / "include").resolve() for r in roots if (r / "include").is_dir()]
        places = [(r / d) for n, r in zip(names, roots) for d in _cppbuild.source_directories(self.root, n)
                  if (r / d).is_dir()]
        suffixes = (*_cppbuild.HEADER_SUFFIXES, *_cppbuild.SOURCE_SUFFIXES)
        arrived = set(moved.values())
        before = {new: old for old, new in moved.items()}

        def existed(path: Path) -> bool:   # 移す前にあったか
            return path in moved or (path.is_file() and path not in arrived)

        def rewritten(file: Path, written: str) -> str | None:
            """file の #include "written" の新しい書き方（変わらなければ None）。"""
            old_place = before.get(file, file)
            for base, local in [(old_place.parent, True)] + [(d, False) for d in include_dirs]:
                found = Path(os.path.normpath(base / written))
                if existed(found):
                    break
            else:
                return None   # 読み込み先が分からない（ほかの場所のもの）
            now = moved.get(found, found)
            if not local:
                if found not in moved:
                    return None
                home = next((d for d in include_dirs if now.is_relative_to(d)), None)
                if home is not None:
                    return now.relative_to(home).as_posix()
            elif file == old_place and now == found:
                return None
            return Path(os.path.relpath(now, file.parent)).as_posix()

        edited = []
        files = dict.fromkeys(p.resolve() for place in places for p in place.rglob("*")
                              if p.is_file() and p.suffix.lower() in suffixes)
        for file in files:
            text = file.read_bytes().decode("utf-8", errors="surrogateescape")
            changed = _INCLUDE.sub(lambda m: (f'{m.group(1)}"{new}"' if (new := rewritten(file, m.group(2))) else m.group(0)),
                                   text)
            if changed != text:
                file.write_bytes(changed.encode("utf-8", errors="surrogateescape"))
                edited.append(file.relative_to(self.root.resolve()).as_posix())
        return edited

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

    def link(self, url: str, *, project: str | None, shared: bool, revision: str | None = None,
             library: str | None = None) -> LinkResult:
        """project を省くと、テスト用を除いてProjectが1つならそれ。library を省くと相手の main。
        既にある依存先の別のライブラリにも足せる（記録の版のまま）。"""
        target = project or self._only_project()
        given = revision
        # 既にある依存先なら、その手元の clone で（短いハッシュも解けるよう取り込み直して）。GitHub のブランチにないなら断る
        existing = next((s for s in _cppbuild.git_sources(self.root) if _cppbuild._same_url(s.url, url)), None)
        resolved = _revisions.commit_for(url, revision, existing.directory if existing else None, command=self.module.command)
        try:
            name, library = _cppbuild.link(self.root, target, url, shared=shared, revision=resolved or revision,
                                           library=library)
        except EcoBuildError as error:
            # 版を確かめられた（resolved）なら、失敗はほかの理由（構成の失敗等）：そのまま
            if given is None or resolved is not None or error.code != ErrorCode.CPPBUILD_ERROR:
                raise
            raise _revisions.unresolved(existing.name if existing else None, url, given, error,
                                        command=self.module.command) from error
        revision = next(s.revision for s in _cppbuild.git_sources(self.root) if s.name == name)
        # 依存先の依存先として既にcloneがあると、CppBuildは記録だけ進める。手元も記録の版に合わせる（作業版は触らない）。
        clone = next((c for c in self._align_dependencies() if c.name == name), None)
        if clone is not None and clone.action == "aligned":
            self._update()
        return LinkResult(name, url, revision, (target,), (library,) if library else (), clone=clone)

    def _only_project(self) -> str:
        """テスト用を除いて、Projectが1つならそれ（ライブラリと組のテスト用だけなら、ライブラリ）。"""
        names = [p.name for p in self.projects() if p.kind != "test"]
        if len(names) != 1:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "リンクするProjectを決められません。",
                                hint=f"--project で指定するか、Projectのディレクトリの中で実行してください"
                                     f"（Project：{'、'.join(names) or 'なし'}）。")
        return names[0]

    def unlink(self, name: str, library: str | None = None) -> LinkResult:
        """手元のcloneは、記録の版のままなら消す（作業中・変更ありなら残す）。library：そのライブラリへのリンクだけを外す
        （記録と clone は残す）。"""
        source = self._source(name)
        if library is not None:
            projects, whole = _cppbuild.unlink_library(self.root, name, library)
            if not whole:
                return LinkResult(name, source.url, source.revision, projects, (library,))
            # 最後の1つだった：記録も外した（リンクのない記録と clone を残さない）
            return LinkResult(name, source.url, source.revision, projects, (library,), self._remove_clone(source),
                              dependency_removed=True)
        projects = _cppbuild.unlink(self.root, name)
        return LinkResult(name, source.url, source.revision, projects, self._remove_clone(source))

    def _remove_clone(self, source) -> bool:
        """外した依存先の clone を、記録の版のままなら消す（作業中・変更ありなら残す）。消したら True。"""
        directory = Path(source.directory)
        removable = directory.is_dir() and self._dependency_state(source).state == "aligned"
        if removable:
            remove_tree(directory)
        return removable

    def dependencies(self) -> tuple[DependencyState, ...]:
        links = _cppbuild.dependency_links(self.root)
        return tuple(replace(self._dependency_state(s), links=tuple(DependencyLink(p, l, g) for p, l, g in links.get(s.name, ())))
                     for s in _cppbuild.git_sources(self.root))

    def dependency_libraries(self, name: str, revision: str | None = None, linked_only: bool = False) -> DependencyLibraries:
        """revision：記録の版でなく、その版（GitHub から一時的に取って読む）。linked_only：リンクしているものだけを、記録から
        （clone がなくても・古い形式でも読める）。"""
        if linked_only:
            source, linked = _cppbuild.linked_libraries_of(self.root, name)
            return DependencyLibraries(name, source.url, source.revision, tuple(
                DependencyLibrary(label, kind, main, True, projects) for label, kind, main, projects in linked))
        users: dict[str, list[str]] = {}
        for project, library, guid in _cppbuild.dependency_links(self.root).get(name, ()):
            users.setdefault(library or guid, []).append(project)
        if revision is not None:
            url = self._any_source(name).url
            found = self.repository_libraries(url, revision)
            return replace(found, name=name, libraries=tuple(replace(l, linked=tuple(users.get(l.name, ())))
                                                             for l in found.libraries))
        source, libraries = _cppbuild.dependency_libraries(self.root, name)
        return DependencyLibraries(name, source.url, source.revision, tuple(
            DependencyLibrary(l.name, l.kind, l.main, l.linkable, tuple(users.get(l.name, ()))) for l in libraries))

    def _any_source(self, name: str):
        """依存先 name（依存先の依存先も）。"""
        source = next((s for s, _ in _cppbuild.all_git_sources(self.root) if s.name == name), None)
        if source is None:
            raise EcoBuildError(ErrorCode.DEPENDENCY_NOT_FOUND, f"依存先 {name} はありません。")
        return source

    def repository_libraries(self, url: str, revision: str | None = None) -> DependencyLibraries:
        """一時的な場所に取って読む（CppBuild の管理ファイルだけを取り出す。終われば消す）。"""
        import tempfile
        # 取った写しには GitHub のブランチが全部ある。手元にだけある（push していない）コミットなら、どこにあるかを添えて断る
        revision = _revisions.commit_for(url, revision, command=self.module.command) or revision
        with tempfile.TemporaryDirectory(prefix="ecobuild-", ignore_cleanup_errors=True) as temporary:
            sha, libraries = _cppbuild.repository_libraries(url, revision, Path(temporary) / "r")
        return DependencyLibraries(None, url, sha, tuple(DependencyLibrary(l.name, l.kind, l.main, l.linkable)
                                                         for l in libraries))

    def all_dependencies(self) -> tuple[DependencyState, ...]:
        return tuple(replace(self._dependency_state(s), via=via) for s, via in _cppbuild.all_git_sources(self.root))

    def dependency_tree(self) -> DependencyTree:
        sources, edges = _cppbuild.dependency_graph(self.root)
        libraries = _cppbuild.dependency_libraries_in_use(self.root)
        nodes = tuple(DependencyNode(s.name, s.url, s.revision, s.present, edges[s.name], libraries.get(s.name, ()),
                                     not s.present and _migrate.is_old(Path(s.directory) / s.path),
                                     _work.read(Git(Path(s.directory)), s.revision) if s.present else None)
                      for s in sources)
        return DependencyTree(self.module.name, tuple(s.name for s in sources if s.recorded_by is None), nodes)

    def update_dependencies(self, name: str | None, revision: str | None = None) -> tuple[DependencyChange, ...]:
        """依存先の記録を、GitHubの最新にする（I-018）。revision：最新でなくこの版に。手元のcloneも合わせ、
        生成ファイルを更新する。"""
        names = [name] if name else [s.name for s in _cppbuild.git_sources(self.root)]
        if name:
            self._source(name)
        updated = {}
        working = []   # 作業版のため記録を進めなかった依存先
        for each in names:
            source = self._source(each)
            before = source.revision
            work = self._work_of(source)
            kept = _snapshot(self.root / _cppbuild.CONFIG_DIRECTORY) if work is not None else None
            # コミットのハッシュなら、手元の clone を取り込み直して長いハッシュに（CppBuild は短いハッシュを手元の clone の
            # 中だけで解く）。GitHub のブランチにない（push していない）なら、どこにあるかを添えて断る
            resolved = _revisions.commit_for(source.url, revision, source.directory, command=self.module.command)
            try:
                updated[each] = (before, _cppbuild.record_revision(self.root, each, resolved or revision))
            except EcoBuildError as error:
                # 版を確かめられた（resolved）なら、失敗はほかの理由：そのまま
                if revision is None or resolved is not None or error.code != ErrorCode.CPPBUILD_ERROR:
                    raise
                raise _revisions.unresolved(each, source.url, revision, error, command=self.module.command) from error
            try:
                recorded = kept is None or self._work_recorded(source, work, updated[each][1])
            except BaseException:
                _restore(kept)
                raise
            if not recorded:
                # 作業版のまま記録を進めない（作業が新しい版に入って＝取り込まれてから。設計_依存先を変える流れ）。
                # 書く前の中身と更新時刻に戻す（GitHub に問い合わせ直さない。前からの未コミットの変更もコミットされない）
                _restore(kept)
                del updated[each]
                if name:
                    raise EcoBuildError(
                        ErrorCode.INVALID_ARGUMENT,
                        f"依存先 {each} は作業版（{work.branch}）で、その作業は{'その版' if revision else 'GitHub の最新'}に"
                        "まだ入っていません。記録は変えませんでした。",
                        hint=f"作業が取り込まれてから {self.module.op('deps update')} {each}。squash・rebase で取り込んだ・"
                             f"作業版をやめて記録を進めるなら {self.module.op('deps work')} {each} --done の後に。")
                working.append(DependencyChange(each, "skipped", f"作業版です（{work.branch}）。記録はそのまま"))
        changes = list(working)
        for change in self._align_dependencies():
            if change.name not in updated:
                continue
            before, after = updated[change.name]
            note = (("最新です" if revision is None else "その版です") if before == after
                    else f"{before[:7]} → {after[:7]}")
            changes.append(DependencyChange(change.name, change.action,
                                            note if change.reason is None else f"{note}（{change.reason}）"))
        self._update()
        return tuple(changes)

    def _work_of(self, source) -> DependencyWorkSource | None:
        """依存先の手元の clone が作業版なら、その作業（_work.read）。"""
        if not (Path(source.directory) / ".git").exists():
            return None
        return _work.read(Git(Path(source.directory), command=self.module.command), source.revision)

    def _work_recorded(self, source, work: DependencyWorkSource, recorded: str) -> bool:
        """作業版の作業（取ってきたコミット。依存先の中で task start したものは今のコミット）が、新しい記録の版に入ったか。"""
        clone = Git(Path(source.directory), command=self.module.command)
        commit = work.commit or clone.rev_parse("HEAD")
        if commit is None:
            return False
        if clone.rev_parse(recorded) is None:
            clone.fetch()
        return commit == recorded or clone.is_ancestor(commit, recorded)

    def dependency_versions(self, name: str, *, branch: str | None = None, count: int = 30) -> DependencyVersions:
        """手元の clone（deps/<名前>）に GitHub から取り込み直して読む（clone がなければ deps sync を案内）。"""
        source = self._source(name)
        directory = Path(source.directory)
        if not (directory / ".git").exists():
            raise EcoBuildError(ErrorCode.DEPENDENCY_NOT_FOUND, f"依存先 {name} の clone がありません。",
                                hint=f"{self.module.op('deps sync')} で取得してから選べます。")
        clone = Git(directory, command=self.module.command)
        clone.run("fetch", "--prune", "--tags", "--force", "origin")
        found = re.search(r"^ref: refs/heads/(\S+)\s+HEAD", clone.output("ls-remote", "--symref", "origin", "HEAD"), re.M)
        branches = tuple(line.removeprefix("origin/") for line in clone.output(
            "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin").splitlines()
            if line.startswith("origin/") and line != "origin/HEAD")
        default = found.group(1) if found else (branches[0] if branches else "")
        shown = branch or default
        if shown not in branches:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"依存先 {name} の GitHub にブランチ {shown} はありません。",
                                hint=(_revisions.branch_hint(source.url, shown, command=self.module.command) or "")
                                + f"GitHub のブランチ：{'、'.join(branches) or 'なし'}")
        # タグの指すコミット：注釈付きのタグは *objectname、軽いタグは objectname
        tags = tuple(DependencyTag(tag, peeled or sha, date) for tag, peeled, sha, date in _fields(clone.output(
            "for-each-ref", "--sort=-creatordate",
            f"--format=%(refname:short){SEP}%(*objectname){SEP}%(objectname){SEP}%(creatordate:iso-strict)", "refs/tags"), 4))
        tagged: dict[str, list[str]] = {}
        for tag in tags:
            tagged.setdefault(tag.sha, []).append(tag.name)
        commits = tuple(DependencyCommit(sha, date, subject, tuple(tagged.get(sha, ()))) for sha, date, subject in _fields(
            clone.output("log", f"--max-count={count}", f"--format=%H{SEP}%cI{SEP}%s", f"refs/remotes/origin/{shown}"), 3))
        return DependencyVersions(name, source.url, source.revision, default, shown, branches, tags, commits)

    def sync_dependencies(self) -> tuple[DependencyChange, ...]:
        changes = self._align_dependencies()
        self._update()
        return changes

    def move_dependency(self, name: str, url: str) -> DependencyChange:
        """記録の URL・場所の名前（deps/<名前>。前の URL の既定の名前なら新しい既定の名前に）・references・手元の clone
        （場所と origin）を新しい名前に合わせ、生成ファイルを作り直す。ほかの依存先が前の URL で記録していれば、同じ
        リポジトリが2つになるので直さない（skipped。そちらを先に直す）。途中で失敗したら記録と clone を戻す。"""
        _cppbuild.fetch_dependencies(self.root)   # 依存先の依存先の記録を読むため、足りない clone を取る
        source = self._source(name)
        users = _cppbuild.recorders_of(self.root, source.url)
        if users:
            return DependencyChange(name, "skipped", f"GitHub で {url} に名前が変わっていますが、依存先 {'、'.join(users)} も"
                                                     "前の URL で記録しているため、そのままにしました（そちらを先に新しい名前に）")
        kept = _snapshot(self.root / _cppbuild.CONFIG_DIRECTORY)
        state = self._dependency_state(source).state
        new_name, before, after = _cppbuild.rename_git_source(self.root, name, url)
        moved = False
        aside = None   # 新しい場所の clone を使うとき、前の clone を脇へ（同じ Project が2つあると構成が止まる）
        try:
            if before != after and before.exists() and after.exists() and _same_repository(after, url):
                # 新しい場所に同じリポジトリの clone がある（依存先の依存先として先に取られた）：そちらを使う。前の clone は
                # 記録の版のままなら消す。作業版・変更があれば、失わないよう直さない
                if state != "aligned":
                    _restore(kept)
                    return DependencyChange(name, "skipped",
                                            f"GitHub で {url} に名前が変わり、新しい場所 {after} に clone がありますが、前の clone "
                                            f"{before} が作業版か変更ありのため直しませんでした（片付けてから、もう一度）")
                aside = self.root / _cppbuild.BUILD_DIRECTORY / f"moved-{before.name}"   # 依存先の置き場所の外（build/ は除外済み）
                if aside.exists():
                    remove_tree(aside)
                aside.parent.mkdir(parents=True, exist_ok=True)
                before.rename(aside)
            elif before != after and before.exists():
                if after.exists():
                    raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"依存先の新しい場所 {after} が既にあります。",
                                        hint="そのフォルダーを片付けてから、もう一度実行してください。")
                before.rename(after)
                moved = True
            if (after / ".git").exists():
                Git(after, command=self.module.command).set_config("remote.origin.url", url)
            self._update()
        except BaseException as error:
            for origin, target in [(after, before)] * moved + [(aside, before)] * (aside is not None):
                try:
                    origin.rename(target)
                except OSError:
                    self.module.repository.notices.append(f"依存先の clone を {origin} から {target} へ戻せませんでした。手で戻してください。")
            if moved and (before / ".git").exists():
                with contextlib.suppress(Exception):
                    Git(before, command=self.module.command).set_config("remote.origin.url", source.url)
            _restore(kept)
            if isinstance(error, OSError):
                raise EcoBuildError(ErrorCode.IN_USE, f"依存先の clone {before} は、ほかのプログラムが使っているため移せません。",
                                    hint="Visual Studio・エディター・端末等で開いていれば閉じてから、もう一度実行してください。",
                                    details=str(error)) from None
            raise
        if aside is not None:
            remove_tree(aside)
        place = f"（場所 {name} → {new_name}）" if new_name != name else ""
        return DependencyChange(new_name, "moved", f"GitHub で名前が変わったため {source.url} → {url}{place}")

    def _align_dependencies(self, only: set[str] | None = None) -> tuple[DependencyChange, ...]:
        """依存先を記録の版に合わせる。作業版（task/のブランチ）・手元で変更やコミットのあるものは触らない。
        only：合わせる依存先をこれに絞る（新しく clone したものは、いつも含める）。"""
        fetched, sources = _cppbuild.fetch_dependencies(self.root)
        changes = []
        for source in sources:
            if source.name in fetched:
                changes.append(DependencyChange(source.name, "cloned"))
                continue
            if only is not None and source.name not in only:
                continue
            clone = Git(source.directory, command=self.module.command)
            head = clone.rev_parse("HEAD")
            branch = clone.current_branch()
            work = _work.read(clone, source.revision)
            if work is not None and work.commit is not None and clone.rev_parse(source.revision) is None:
                # 記録の版がまだ手元にない（取り込まれて deps update した直後等）：取り込んで、作業が記録に入ったかを確かめ直す
                clone.fetch()
                work = _work.read(clone, source.revision)
            if work is not None:
                # 作業版（deps work・依存先の中で task start をしたもの〔I-019〕）。記録の版へ切り替えない。
                changes.append(DependencyChange(source.name, "skipped", f"作業版です（{work.branch}）"))
                continue
            _work.forget(clone)   # 作業版でない：残った作業版の設定（手で切り替えた等）は古いので消す
            if head == source.revision and branch is None:
                changes.append(DependencyChange(source.name, "unchanged"))
                continue
            if not clone.working_tree().clean:
                changes.append(DependencyChange(source.name, "skipped", "未コミットの変更があります"))
                continue
            if _unpublished(clone, head):
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
        work = _work.read(clone, source.revision)
        clean = clone.working_tree().clean
        if work is not None:
            state = "working"
            work = replace(work, modified=not clean)
        elif not clean:
            state = "modified"
        else:
            state = "aligned" if head == source.revision else "differs"
        return DependencyState(source.name, source.url, source.revision, head, state,
                               branch or (work.branch if work is not None else None), work=work)

    def work_dependency(self, name: str, *, task: int | None = None, branch: str | None = None,
                        done: bool = False) -> DependencyWorkResult:
        """依存先の手元の clone を作業版にする・取り直す・記録の版に戻す（_work）。記録（git_sources の版）は変えない。

        作業版の clone は、取ってきたコミットで切り離したまま（ブランチを作らない。deps/ の中で ecobuild を動かしても、
        依存先のタスクブランチに見えず、task commit・push で作りかけが依存先の GitHub に出ない）。"""
        source = self._any_source(name)
        directory = Path(source.directory)
        command = self.module.command
        if not (directory / ".git").exists():
            if done:
                return DependencyWorkResult(name, "done", None, source.revision, None, self.sync_dependencies())
            _cppbuild.fetch_dependencies(self.root)   # 記録の版で clone してから切り替える
        clone = Git(directory, command=command)
        current = _work.read(clone, source.revision)
        previous = clone.rev_parse("HEAD")
        if not clone.working_tree().clean:
            raise EcoBuildError(ErrorCode.DIRTY_WORKING_TREE, f"依存先 {name} の手元の clone（{directory}）に、未コミットの変更があります。",
                                hint="deps/ の中で直したものを消さないよう止めました。依存先を変えるなら、依存先のモジュールの"
                                     "タスクで直してください（要らない変更なら、その clone の中で消してから、もう一度）。")
        if done:
            return self._end_work(source, clone, current, previous)
        if task is None and branch is None:
            if current is None:
                raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"依存先 {name} は作業版ではありません。",
                                    hint=f"作業版にするには {self.module.op('deps work')} {name} --task <依存先のタスクの番号>"
                                         "（か --branch <ブランチ>）。")
            branch = current.branch
        wanted, origin, place = _work.locate(name, source.url, task=task, branch=branch, command=command)
        commit = _work.fetch(clone, place, wanted)
        # deps/ の中でコミットしたもの（取ってきた先にも GitHub にもないもの）を、切り替えで消さない
        if previous not in (commit, source.revision, current.commit if current else None) \
                and not clone.is_ancestor(previous, commit) and _unpublished(clone, previous):
            raise _would_lose(name, current)
        clone.run("switch", "--quiet", "--detach", commit)
        work = DependencyWorkSource(wanted, wm.task_number(wanted), origin, place, commit)
        _work.remember(clone, work)
        if origin == _work.LOCAL and _work.github_ahead(clone, source.url, wanted, commit):
            self.module.repository.notices.append(
                f"GitHub の {wanted} には、このPCの作業空間（{place}）にないコミットがあります。作業空間で取り込む"
                f"（{self.module.op('sync')}）と、それも使えます。")
        # 作業版が記録する依存先の依存先（新しく足したもの・版を上げたもの）も、その記録に合わせる
        # ほかの依存先（手で別の版にしたもの等）は触らない
        changes = tuple(c for c in self._align_dependencies(self._recorded_under(name))
                        if c.name != name and c.action != "unchanged")
        self._update()
        if current is not None and current.branch == wanted:
            action = "unchanged" if previous == commit else "refreshed"
        else:
            action = "switched"
        return DependencyWorkResult(name, action, work, source.revision, previous, changes)

    def _recorded_under(self, name: str) -> set[str]:
        """依存先 name が記録する依存先（その先も）の名前。"""
        recorders = {source.name: via for source, via in _cppbuild.all_git_sources(self.root)}
        found: set[str] = set()
        for each in recorders:
            at = recorders[each]
            seen = set()
            while at is not None and at not in seen:
                if at == name:
                    found.add(each)
                    break
                seen.add(at)
                at = recorders.get(at)
        return found

    def _end_work(self, source, clone: Git, current, previous: str | None) -> DependencyWorkResult:
        """作業版をやめ、記録の版に戻す（deps sync と同じく、ほかの依存先も記録の版に合わせる）。"""
        if previous not in (source.revision, current.commit if current else None) and _unpublished(clone, previous):
            raise _would_lose(source.name, current)
        if clone.rev_parse(source.revision) is None:
            clone.fetch()
        clone.run("switch", "--quiet", "--detach", source.revision)
        _work.forget(clone)
        return DependencyWorkResult(source.name, "done", None, source.revision, previous, self.sync_dependencies())


def _same_repository(clone: Path, url: str) -> bool:
    """clone の origin が url と同じリポジトリか（末尾の / ・.git の違い、大文字・小文字は同じとみなす）。"""
    try:
        origin = Git(clone).get_config("remote.origin.url") or ""
    except Exception:
        return False
    from ecobuild.workspaces import identity
    return bool(origin) and identity(origin) == identity(url)   # GitHub なら 所有者/名前 で（https・ssh の違いは同じ）


def _snapshot(directory: Path) -> dict[Path, tuple[bytes, int, int]]:
    """directory の下のファイルの中身と更新時刻（_restore で書き戻す）。"""
    kept = {}
    for path in directory.rglob("*"):
        if path.is_file():
            stat = path.stat()
            kept[path] = (path.read_bytes(), stat.st_atime_ns, stat.st_mtime_ns)
    return kept


def _restore(kept: dict[Path, tuple[bytes, int, int]] | None) -> None:
    """_snapshot の中身と更新時刻に戻す（変わったものだけ）。"""
    for path, (data, atime, mtime) in (kept or {}).items():
        try:
            if path.read_bytes() == data:
                continue
        except OSError:
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        os.utime(path, ns=(atime, mtime))


def _unpublished(clone: Git, head: str | None) -> bool:
    """依存先の clone の head が、GitHub のどのブランチにもない（deps/ の中でコミットした等）。取り込み直して確かめる。"""
    if head is None:
        return False
    clone.fetch()
    return not clone.output("branch", "--remotes", "--contains", head)


def _would_lose(name: str, current) -> EcoBuildError:
    where = f"（{current.branch}）" if current is not None else ""
    return EcoBuildError(ErrorCode.COMMITS_WOULD_BE_LOST,
                         f"依存先 {name} の手元の clone{where}に、取ってくる先にも GitHub にもないコミットがあります。",
                         hint="依存先を変えるのは、依存先のモジュールのタスク（その作業空間）でしてください。deps/ の中で"
                              "コミットしたものが要るなら、その clone から push してから、もう一度実行してください。")
