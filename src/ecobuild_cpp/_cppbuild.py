"""CppBuild の呼び出し（cpp 型の内部）。"""

from __future__ import annotations

import os
import shlex
import subprocess
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from cppbuild import (ARCHITECTURES, CONFIGURATIONS, CPP_STANDARDS, GENERATORS, INHERIT, AlreadyRegisteredError,
                      CMakeSettings, InvalidValueError, NoMainProjectError, NotRegisteredError, ProjectBuildSettings,
                      ProjectType, Solution, SolutionBuildSettings, SolutionFolderSettings, ToolSettings)

from cppbuild import engine as _engine
from cppbuild import logs as _logs
from cppbuild import tooling as _tooling
from cppbuild import workspace as _workspace

from ecowork.git import CLONE_CONFIG, Git

from ecobuild.config import DIRECTORY
from ecobuild.errors import EcoBuildError, operation

from .errors import ErrorCode
from ecobuild.fsutil import remove_tree
from ecobuild.results import ProjectSummary

# CppBuildのSolutionの .cppbuild（設定と生成ファイルのすべて）。ECOBuildのファイルの置き場所 .ecobuild/ の直下に置き、
# パスの基準（CppBuildの base_directory）はモジュールのルートにする（Projectはルートの直下）。
CONFIG_NAME = ".cppbuild"
CONFIG_DIRECTORY = f"{DIRECTORY}/{CONFIG_NAME}"
_CONFIG_PARTS = Path(CONFIG_DIRECTORY).parts
_TO_ROOT = "/".join([".."] * len(_CONFIG_PARTS))   # .cppbuild からモジュールのルートへ
DEPENDENCY_DIRECTORY = "deps"   # 依存先のcloneの置き場所（.gitignore で除外）
# CMakeのビルドツリー（中間ファイル）の置き場所。CppBuildの既定（.cppbuild/output/intermediate）より
# 短い、モジュール直下の build/ にする（Windowsの260文字の制限への対策）。
# CppBuildの設定は.cppbuildからの相対で、保存されないため、Solutionを開くたびに設定する。
BUILD_DIRECTORY = "build"
GENERATED_FILE_NAMES = ("CMakeLists.txt", "CppBuildTopLevel.cmake")

# CppBuildのファイルテンプレートとして登録する既定の素材（名前 → 素材ファイル）
TEMPLATES = {
    "header": "header.h",
    "source": "source.cpp",
    "pch": "pch.h",
    "test": "test.cpp",
    "main": "main.cpp",
    "app": "app.cpp",        # ライブラリをリンクしない実行ファイルの main
    "bench": "bench.cpp",
    "unit_test": "unit_test.cpp",
}

# module new の --kind：最初に作るProject（app：実行ファイル、library：静的ライブラリとテスト用、
# shared：共有ライブラリ〔Windows は DLL〕とテスト用、none：作らない）
NEW_KINDS = ("app", "library", "shared", "none")

# project add の種類 → CppBuildの種類
PROJECT_KINDS = {
    "library": ProjectType.STATIC_LIBRARY,
    "shared": ProjectType.SHARED_LIBRARY,
    "app": ProjectType.EXECUTABLE,
    "test": ProjectType.TEST,
    "bench": ProjectType.EXECUTABLE,
}
# 種類のうちライブラリ（組のテスト用Projectを作る・--link は使えない）
LIBRARY_KINDS = ("library", "shared")
# project set --kind で変えられる種類（テスト用・性能測定は、リンクするライブラリが決まらないので除く）
CHANGEABLE_KINDS = ("app", "library", "shared")
# ライブラリの形式（project set --for・project link --as・ビルド設定の type）→ CppBuildの種類
LIBRARY_TYPES = {
    "static": ProjectType.STATIC_LIBRARY,
    "shared": ProjectType.SHARED_LIBRARY,
    "interface": ProjectType.INTERFACE_LIBRARY,
}
# 構成・C++の規格（既定は20）・アーキテクチャ（省略時はホスト・コンパイラの既定）・生成器（省略時はOSごとの既定）は、
# CppBuildが受け付ける値そのもの（CppBuildが増やしても、ここは書き換えない）。
HEADER_SUFFIXES = (".h", ".hpp", ".hh", ".hxx")
SOURCE_SUFFIXES = (".cpp", ".cc", ".cxx")


@dataclass(frozen=True)
class ProjectOptions:
    """Projectごとの上書き（名前付きビルド設定の [profiles.<名前>.projects.<Project>]）。None は全体の設定のまま。"""
    type: str | None = None                  # static・shared・interface（ライブラリだけ）
    cpp_standard: int | None = None
    artifact_directory: str | None = None    # 成果物の置き場所（ビルドツリーからの相対）
    test_parallel: int | None = None
    googletest_archive: str | None = None


@dataclass(frozen=True)
class BuildOptions:
    """1回のビルド等の設定（名前付きビルド設定から作る）。None はCppBuildの既定。"""
    configuration: str = "Debug"
    parallel: int = 1
    shared: bool = False      # ライブラリ（依存先を含む）を共有ライブラリにする
    architecture: str | None = None
    cpp_standard: int | None = None
    generator: str | None = None
    toolset: str | None = None
    c_compiler: str | None = None
    cxx_compiler: str | None = None
    toolchain_file: str | None = None
    windows_sdk: str | None = None           # Windows SDKの版（例：10.0.22621.0。MSVCだけ）
    test_parallel: int = 1
    test_continue_on_failure: bool = True
    googletest_archive: str | None = None    # GoogleTestのZIP（オフライン用）
    fetch_git: bool = True                   # 足りない依存先をビルドの前にcloneする
    cmake: str | None = None                 # ツールのパス（このPCの設定 ecobuild config。既定はPATH）
    ctest: str | None = None
    projects: tuple[tuple[str, ProjectOptions], ...] = ()
    command: str = ""                        # ヒントに書くプログラム名（Module.command）


@dataclass(frozen=True)
class ProcessOutput:
    command: str
    returncode: int
    output: str


@dataclass(frozen=True)
class BuildOutcome:
    success: bool
    processes: tuple[ProcessOutput, ...]
    artifacts: tuple[Path, ...] = ()


@dataclass(frozen=True)
class TestCase:
    name: str
    status: str


@dataclass(frozen=True)
class TestOutcome:
    success: bool
    cases: tuple[TestCase, ...]
    processes: tuple[ProcessOutput, ...]
    diagnostics: tuple[str, ...] = ()


def open_solution(root: Path) -> Solution:
    try:
        solution = Solution.open(root / CONFIG_DIRECTORY)
        solution.set_build_settings(_solution_settings())
        return solution
    except Exception as error:  # CppBuildの例外は種類が多いので、まとめて変換する
        raise _cppbuild_error("CppBuildのSolutionを開けません。", error) from error


def create_module_solution(root: Path, name: str, kind: str, project: str | None = None, *,
                           test: bool = True) -> Solution:
    """Solutionと、最初のProjectを作る（生成はしない）。kind：app＝実行ファイル <Project名>、
    library＝静的ライブラリ <Project名> とテスト用 <Project名>Test（test が偽なら作らない）、shared＝同じく共有ライブラリ、
    none＝Projectを作らない。
    Project名は project（省略時はモジュール名）。

    CppBuildは最初に作ったProjectを main_project にし、他のモジュールからリンクされるのはそれだけ
    （実行ファイル・なしなら、他のモジュールからはリンクできない）。
    """
    try:
        solution = Solution.create(root / DIRECTORY, name, base_directory="..")
        data = solution.settings.get()
        data.dependency_directories = [DEPENDENCY_DIRECTORY]
        data.solution_folders = SolutionFolderSettings()
        solution.settings.save(data)
        _register_templates(solution)
        if kind == "app":
            _create_linked(solution, project or name, "app", None)
        elif kind in LIBRARY_KINDS:
            _create_library(solution, project or name, test=test, kind=kind)
        return solution
    except EcoBuildError:
        raise
    except Exception as error:
        raise _cppbuild_error("CppBuildでSolutionを作成できません。", error) from error


def _create_library(solution: Solution, name: str, *, test: bool, kind: str = "library") -> list[str]:
    """ライブラリ（ヘッダー include/<名前>/<名前>.h と src/<名前>.cpp）と、test ならテスト用 <名前>Test。
    kind：library＝静的、shared＝共有（どちらも Windows で関数を書き出す設定にする。_add_library_header）。"""
    project = solution.add_project(name, name, PROJECT_KINDS[kind])
    header = library_header(name)
    _add_library_header(project, f"include/{header}")
    project.add_file(f"src/{name}.cpp", template_name="source", replacements={"header": header}, auto_update=False)
    files = [f"{name}/include/{header}", f"{name}/src/{name}.cpp"]
    if test:
        files += _create_linked(solution, test_project_of(name), "test", name, suite=name)
    return files


def _create_linked(solution: Solution, name: str, kind: str, library: str | None, *, suite: str | None = None) -> list[str]:
    """実行ファイル・テスト・性能測定のProject。library があればリンクし、そのヘッダーを読み込む素材を置く。"""
    project = solution.add_project(name, name, PROJECT_KINDS[kind])
    if library is None:   # app だけ（test・bench はライブラリが要る）
        project.add_file("src/main.cpp", template_name="app", auto_update=False)
        return [f"{name}/src/main.cpp"]
    other = solution.get_project(library)   # ライブラリの作成時の形式（静的・共有）でリンクする
    project.settings.link_project(other, other.settings.get().initial_type)
    template, file_name = {"app": ("main", "main.cpp"), "test": ("test", f"{name}.cpp"),
                           "bench": ("bench", "bench.cpp")}[kind]
    replacements = {"header": library_header(library)}
    if kind == "test":
        replacements["suite"] = suite or name
    project.add_file(f"src/{file_name}", template_name=template, replacements=replacements, auto_update=False)
    return [f"{name}/src/{file_name}"]


def template_path(root: Path, name: str) -> str:
    """ファイルテンプレートの素材の場所（モジュールからの相対）。CppBuildは .cppbuild/templates の下の名前で記録する。"""
    return f"{CONFIG_DIRECTORY}/templates/{name}"


def library_header(library: str) -> str:
    """ECOBuildが作ったライブラリのヘッダー（include/ からの相対）。"""
    return f"{library}/{library}.h"


def check_project_name(name: str) -> None:
    """CMakeのターゲット名はProject名そのもの（CppBuild e83c7a0〜）。CMake・生成器が使う名前（test・all 等。
    大文字小文字は区別しない）にはできない（CppBuildも構成のときに止めるが、英語で、作った後になる）。"""
    if name.casefold() in _workspace.RESERVED:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"Project名 {name} は使えません（CMakeが使う名前です）。",
                            hint="別の名前にしてください（ALL_BUILD・test・all・install 等と、大文字小文字の違いだけの名前も使えません）。")


def check_new_projects(name: str, kind: str, project: str | None, *, test: bool) -> None:
    """module new で作るProjectの名前を、作る前に確かめる（create_module_solution と同じ決め方）。"""
    if kind == "none":
        return
    first = project or name
    for each in [first] + ([test_project_of(first)] if kind in LIBRARY_KINDS and test else []):
        check_project_name(each)


def test_project_of(library: str) -> str:
    """ライブラリと組のテスト用Project（ライブラリを作るときに一緒に作る。file add のテストの置き場所）。"""
    return f"{library}Test"


def update(root: Path, options: BuildOptions | None = None) -> BuildOutcome:
    """構成と生成ファイル（CMakeLists.txt等）を最新にする。options：構成に使うビルド設定（生成器等。既定はCppBuildの既定）。"""
    solution = open_solution(root)
    if options is not None:
        _apply_options(solution, options)
    if options is None or options.fetch_git:
        _fetch_missing(solution)
    try:
        _ensure_solution_folders(solution)
        report = solution.update()
    except Exception as error:
        raise _cppbuild_error("CppBuildの構成に失敗しました。", error) from error
    # Solution.updateはOperationReport、Project.updateはUpdateReportを返す。
    processes = report.processes if hasattr(report, "processes") else (report.process,)
    outcome = BuildOutcome(report.success, tuple(_process(p) for p in processes))
    if not outcome.success:
        raise EcoBuildError(ErrorCode.CPPBUILD_ERROR, "CppBuildの構成に失敗しました。",
                            details=_joined(outcome.processes))
    return outcome


def build(root: Path, *, project: str | None, options: BuildOptions, action: str = "build") -> BuildOutcome:
    """build・clean・rebuild。"""
    target = _target(root, project, options)
    try:
        report = getattr(target, action)()
    except Exception as error:
        raise _cppbuild_error("ビルドを実行できません。", error) from error
    outcome = BuildOutcome(report.success, tuple(_process(p) for p in report.processes),
                           tuple(getattr(report, "artifacts", ())))
    if not outcome.success:
        message = "ビルドに失敗しました。" if action != "clean" else "クリーンに失敗しました。"
        raise EcoBuildError(ErrorCode.BUILD_FAILED, message, details=_joined(outcome.processes))
    return outcome


def test(root: Path, *, project: str | None, options: BuildOptions) -> TestOutcome:
    """テスト用のProjectがなければ、何もせずに成功（ケースなし）。"""
    if project is None and not _tests(open_solution(root)):
        return TestOutcome(True, (), ())
    target = _target(root, project, options)
    try:
        report = target.test()
    except Exception as error:
        raise _cppbuild_error("テストを実行できません。", error) from error
    reports = report.projects if report.projects else (report,)
    cases = tuple(TestCase(c.name, c.status) for r in reports for c in r.cases)
    processes = tuple(_process(p) for r in reports for p in r.processes)
    diagnostics = tuple(d for r in reports for d in r.diagnostics)
    outcome = TestOutcome(report.success, cases, processes, diagnostics)
    if not outcome.success:
        failed = [c.name for c in cases if c.status not in {"passed", "skipped"}]
        raise EcoBuildError(ErrorCode.TEST_FAILED,
                            "テストに失敗しました。" + (f"（{', '.join(failed)}）" if failed else ""),
                            details={"cases": [c.__dict__ for c in cases], "diagnostics": list(diagnostics),
                                     "output": _joined(processes)})
    return outcome


def run(root: Path, *, project: str | None, options: BuildOptions, arguments: str) -> BuildOutcome:
    solution = open_solution(root)
    name = project or _single_executable(solution)
    if (project is not None and project in solution.settings.get().projects
            and ProjectType.EXECUTABLE not in solution.get_project(project).settings.get().types):
        raise EcoBuildError(ErrorCode.RUN_FAILED, f"Project {project} は実行ファイルではありません。",
                            hint=f"実行ファイルのProject：{'、'.join(_executables(solution)) or 'なし'}")
    target = _target(root, name, options, run_arguments=shlex.split(arguments))
    try:
        report = target.run()
        report = report.wait() if hasattr(report, "wait") else report
    except Exception as error:
        raise _cppbuild_error("実行できません。", error) from error
    outcome = BuildOutcome(report.success, tuple(_process(p) for p in report.processes))
    if not outcome.success:
        failed = next(i for i, p in enumerate(outcome.processes) if p.returncode != 0)
        if failed < len(outcome.processes) - 1:
            # 実行の前のビルド（構成）で失敗した。
            raise EcoBuildError(ErrorCode.BUILD_FAILED, "ビルドに失敗しました。", details=_joined(outcome.processes))
        program = outcome.processes[failed]
        raise EcoBuildError(ErrorCode.RUN_FAILED, f"{name} が終了コード {program.returncode} で終了しました。",
                            details={"returncode": program.returncode, "output": program.output})
    return outcome



@contextmanager
def program_output(write: Callable[[str], None], *, tools: bool = True) -> Iterator[None]:
    """この中で CppBuild が動かす子プロセスの出力を、1行ずつ write に渡す（改行なし。結果の output は今までどおり全部）。
    tools：CMake・CTest（構成・ビルド・テスト）の出力も渡す。偽なら、実行するプログラムの出力だけ。

    CppBuild には出力を逐次受け取る口がない（子プロセスはどれも cppbuild.engine.process で、終わるまでためる）ので、
    その間だけ、同じ形の結果（ProcessReport）を返す、読みながら渡すものに替える。CMake・CTest は cppbuild.tooling.process
    を通るので、それで分ける。CppBuild に口ができたら、それに替える。
    """
    original, original_tool, lock, inside_tool = _engine.process, _tooling.process, threading.Lock(), threading.local()

    def tool(*args, **kwargs):
        inside_tool.on = True
        try:
            return original_tool(*args, **kwargs)
        finally:
            inside_tool.on = False

    def process(command, cwd, env=None):
        if not tools and getattr(inside_tool, "on", False):
            return original(command, cwd, env)
        command = tuple(str(arg) for arg in command)
        with _logs.command(command, cwd, env) as finished:
            child = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False,
                                     env=dict(os.environ) if env is None else env)
            data = []
            with child.stdout:
                for line in child.stdout:
                    data.append(line)
                    with lock:   # 並べて動かす実行（run_parallel）の行が混ざらないように
                        for text in _engine.decode_output(line).rstrip("\n").split("\n"):
                            write(text)
            returncode = child.wait()
            output = _engine.decode_output(b"".join(data))
            finished(returncode, output)
        return _engine.ProcessReport(command, returncode, output)

    _engine.process, _tooling.process = process, tool
    try:
        yield
    finally:
        _engine.process, _tooling.process = original, original_tool


@dataclass(frozen=True)
class DependencySource:
    name: str
    directory: Path
    revision: str           # 記録されたコミット
    present: bool


def fetch_dependencies(root: Path) -> tuple[tuple[str, ...], tuple[DependencySource, ...]]:
    """足りない依存先を記録の版でcloneし、（今回cloneした名前, 全依存先）を返す。"""
    solution = open_solution(root)
    try:
        with _clone_config():
            report = solution.fetch_git_sources()
    except Exception as error:
        raise _cppbuild_error("依存先を取得できません。", error) from error
    _write_clone_config(Path(s.directory) for s in report.sources)   # 前の版が clone したものも（CRLF で取り出した等）
    sources = tuple(DependencySource(s.name, Path(s.directory), s.revision, True) for s in report.sources)
    return tuple(report.fetched), sources


def project_at(root: Path, path: Path) -> str | None:
    """pathが属するProjectの名前。どのProjectにも属さなければNone。"""
    solution = open_solution(root)
    path = path.resolve()
    for name in solution.settings.get().projects:
        directory = Path(solution.get_project(name).root).resolve()
        if path == directory or directory in path.parents:
            return name
    return None


def is_generated(relative_path: str) -> bool:
    """CppBuildの生成ファイル（管理ファイルから作り直せるもの）か。生成ファイルは .cppbuild の中にだけある。"""
    parts = Path(relative_path).parts
    return is_generated_or_managed(relative_path) and parts[-1] in GENERATED_FILE_NAMES


def is_generated_or_managed(relative_path: str) -> bool:
    """CppBuildの生成ファイル・管理ファイル（コミット対象）か。.cppbuild の中の、出力（output）・ロック（operations）以外。"""
    parts = Path(relative_path).parts
    inside = parts[len(_CONFIG_PARTS):]
    return parts[:len(_CONFIG_PARTS)] == _CONFIG_PARTS and bool(inside) and inside[0] not in ("output", "operations")


# Project ---------------------------------------------------------------------

def list_projects(root: Path) -> tuple[ProjectSummary, ...]:
    solution = open_solution(root)
    by_guid = _guid_names(solution)
    for source in solution.git_sources():
        if source.present:  # 依存先のProjectは「依存先の名前/Project名」で示す
            by_guid.update({guid: f"{source.name}/{name}"
                            for guid, name in _guid_names(Solution.open(source.config)).items()})
    result = []
    for name, directory in solution.settings.get().projects.items():
        data = solution.get_project(name).settings.get()
        links = tuple(by_guid.get(d.project_guid, d.project_guid) for d in data.dependencies.values()
                      if hasattr(d, "project_guid"))
        result.append(ProjectSummary(name, data.initial_type.value, directory, links, tuple(data.source_directories)))
    return tuple(result)


def add_project(root: Path, name: str, kind: str, *, link: str | None = None, test: bool = True) -> tuple[str, ...]:
    """Projectを作る。作ったファイルを返す。

    library（静的）・shared（共有）：ライブラリと、test ならテスト用 <名前>Test（I-022）。app・test・bench：link のライブラリ
    （省略時は、ライブラリが1つならそれ）をリンクする。test・bench にはライブラリが要る。app はなくてもよい。
    """
    if kind not in PROJECT_KINDS:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"種類 {kind} はありません。",
                            hint=f"{'・'.join(PROJECT_KINDS)} のどれかを指定してください。")
    solution = open_solution(root)
    existing = solution.settings.get().projects
    for each in [name] + ([test_project_of(name)] if kind in LIBRARY_KINDS and test else []):
        check_project_name(each)
        if each in existing:
            raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"Project {each} は既にあります。")
        if (root / each).exists():
            raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{root / each} は既に存在します。")
    library = None
    if kind in LIBRARY_KINDS:
        if link:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"--link は {kind} では使えません。")
    else:
        library = _library_to_link(solution, link)
        if library is None and kind != "app":
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                                f"{'テスト' if kind == 'test' else '性能測定'}のProjectには、リンクするライブラリが要ります。",
                                hint="先に project add <名前> --kind library でライブラリを作ってください。")
    try:
        _ensure_templates(solution)
        files = (_create_library(solution, name, test=test, kind=kind) if kind in LIBRARY_KINDS
                 else _create_linked(solution, name, kind, library))
        solution.update()
        return tuple(files)
    except EcoBuildError:
        raise
    except Exception as error:
        raise _cppbuild_error(f"Project {name} を作れません。", error) from error


def _library_to_link(solution: Solution, link: str | None) -> str | None:
    """リンクするライブラリ：指定があればそれ（ライブラリか確かめる）、なければライブラリが1つならそれ。"""
    libraries = [name for name in solution.settings.get().projects
                 if ProjectType.STATIC_LIBRARY in solution.get_project(name).settings.get().types]
    if link:
        _require_project(solution, link)
        if link not in libraries:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"Project {link} はライブラリではありません。",
                                hint=f"ライブラリ：{'、'.join(libraries) or 'なし'}")
        return link
    if len(libraries) > 1:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "リンクするライブラリを決められません。",
                            hint=f"--link で指定してください（ライブラリ：{'、'.join(libraries)}）。")
    return libraries[0] if libraries else None


def remove_project(root: Path, name: str) -> bool:
    """Projectを、他のProjectからのリンクごと外す（ファイルは呼び出し側が消す）。

    main_project（他のモジュールからリンクされるもの）なら、先に main_project をなしにする（CppBuildは
    main_project のままでは外せない）。そうしたら True。
    """
    solution = open_solution(root)
    _require_project(solution, name)
    try:
        with _transaction(solution, f"Project {name} を外せません。"):
            data = solution.settings.get()
            was_main = data.main_project == name
            if was_main:
                data.main_project = None
                solution.settings.save(data)
            guid = solution.get_project(name).settings.get().guid
            for other in solution.projects():
                if other.name == name:
                    continue
                for key, dependency in list(other.settings.get().dependencies.items()):
                    if getattr(dependency, "project_guid", None) == guid:
                        other.settings.unlink(key)
            solution.remove_project(name)
    except EcoBuildError:
        raise
    except Exception as error:
        raise _cppbuild_error(f"Project {name} を外せません。", error) from error
    return was_main


def change_kind(root: Path, name: str, kind: str, *, test: bool = True, command: str = "") -> tuple[str, ...]:
    """Projectの種類を変える（app・library・shared）。足したファイルを返す（同じ種類なら何もしない）。

    CppBuildは作った後に種類（initial_type）を変えられないので、同じ名前・場所・設定のまま外して作り直す
    （1つのトランザクション。失敗したら管理ファイル・生成ファイルは元に戻る）。保つもの：ソース、定義・インクルード等の設定、
    このProjectのリンク（依存先のモジュールへのリンクは張り直す）、使う側のリンク（ライブラリどうしのときだけ。作成時の形式で
    リンクしていたものは新しい形式で）、main、ソリューションフォルダー。変わるもの：GUID（CppBuildが作り直すたびに付け直す）と
    Projectの並び（最後になる）。そのため、他のモジュールからリンクされうる main のライブラリは、ライブラリどうしでも変えない。

    ライブラリにするとき：入口の関数・GUIアプリの設定を外し、project add と同じく、Windowsですべての関数を書き出し、
    ないファイル（include/<名前>/<名前>.h・src/<名前>.cpp）を置き、実行ファイルからで test なら組のテスト用 <名前>Test を作る
    （その名前のProject・ディレクトリが既にあれば作らない）。
    実行ファイルにするとき：使う側のProject・main なら断る。入口は main にし、src/main.cpp がなければ置く。
    """
    if kind not in CHANGEABLE_KINDS:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"種類 {kind} には変えられません。",
                            hint=f"{'・'.join(CHANGEABLE_KINDS)} のどれかを指定してください。")
    solution = open_solution(root)
    _require_project(solution, name)
    project = solution.get_project(name)
    data = project.settings.get()
    target = PROJECT_KINDS[kind]
    if data.initial_type == target:
        return ()
    if data.initial_type == ProjectType.TEST:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{name} はテスト用のProjectなので、種類を変えられません。")
    module = solution.settings.get()
    library = data.initial_type in LIBRARY_TYPES.values()
    to_library = kind in LIBRARY_KINDS
    main = module.main_project
    is_main = main == name
    users = [(other, key, dependency) for other in solution.projects() if other.name != name
             for key, dependency in other.settings.get().dependencies.items()
             if getattr(dependency, "project_guid", None) == data.guid]
    if not to_library and users:
        names = sorted({other.name for other, _, _ in users})
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                            f"{name} は {'、'.join(names)} がリンクしているので、実行ファイルにできません。",
                            hint=f"先にリンクを外してください（{operation(command, 'project unlink')} {name} --project <Project>"
                                 f"。テスト用のProjectなら {operation(command, 'project remove')} で消せます）。",
                            details=names)
    if is_main and (not to_library or library):
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                            f"{name} は他のモジュールからリンクされるProject（main）なので、種類を変えられません。",
                            hint=("種類を変えると作り直しになり、他のモジュールからのリンクが切れます。"
                                  if library and to_library else "") +
                                 f"先に {operation(command, 'module settings')} --no-main で main をなしにしてください"
                                 + ("（ビルドごとに静的・共有を切り替えるなら profile の type か project link --as で足ります）。"
                                    if library and to_library else "。"))
    fresh = deepcopy(data)
    used = data.types[data.initial_type]   # 今の種類の設定（ライブラリなら作成時の形式の設定）を引き継ぐ
    if to_library:
        if not library:
            fresh.types = {each: deepcopy(used) for each in LIBRARY_TYPES.values()}
            fresh.windows_export_all_symbols = True   # project add のライブラリと同じ（_add_library_header）
        fresh.entry_point, fresh.gui = None, False
    else:
        fresh.types = {target: deepcopy(used)}
        fresh.windows_export_all_symbols = False
    fresh.initial_type = target
    # 依存先のモジュールへのリンクは、外すとそのモジュールの記録（references）も消えるので、作り直した後に張り直す。
    references = module.references
    external = {key: dependency for key, dependency in data.dependencies.items()
                if getattr(dependency, "project_guid", None) in references}
    fresh.dependencies = {key: value for key, value in data.dependencies.items() if key not in external}
    folders = module.solution_folders
    folder = None if folders is None else folders.project_folders.get(name)
    directory = module.projects[name]
    test_name = test_project_of(name)
    make_test = to_library and not library and test and test_name not in module.projects and not (root / test_name).exists()
    if make_test:
        check_project_name(test_name)
    message = f"Project {name} の種類を変えられません。"
    files: list[str] = []
    try:
        _ensure_templates(solution)
        with _transaction(solution, message):
            if is_main:
                module.main_project = None
                solution.settings.save(module)
            for other, key, _ in users:
                other.settings.unlink(key)
            solution.remove_project(name)
            remade = solution.add_project(directory, name, target, settings=fresh)
            for dependency in external.values():
                place = solution.root / references[dependency.project_guid].solution_directory
                remade.settings.link_solution(place, dependency.project_type)
            for other, _, dependency in users:   # 作成時の形式でリンクしていたものは、新しい形式で
                as_type = target if dependency.project_type == data.initial_type else dependency.project_type
                other.settings.link_project(remade, as_type)
            # main は元のとおりに（CppBuildは、Projectがほかにない Solution に足したProjectを main にする）。
            module = solution.settings.get()
            if module.main_project != main or folder is not None:
                module.main_project = main
                if folder is not None:
                    module.solution_folders.project_folders[name] = folder
                solution.settings.save(module)
            files = _place_kind_files(solution, remade, name, to_library)
            if make_test:
                files += _create_linked(solution, test_name, "test", name, suite=name)
    except EcoBuildError:
        raise
    except Exception as error:
        raise _cppbuild_error(message, error) from error
    return tuple(files)


def _place_kind_files(solution: Solution, project, name: str, to_library: bool) -> list[str]:
    """種類を変えたProjectに、project add で置くもののうち、ないファイルを置く（あるものは上書きしない）。"""
    wanted = ([(f"include/{library_header(name)}", "header", None),
               (f"src/{name}.cpp", "source", {"header": library_header(name)})] if to_library
              else [("src/main.cpp", "app", None)])
    files = []
    for path, template, replacements in wanted:
        if not (project.root / path).exists():
            project.add_file(path, template_name=template, replacements=replacements, auto_update=False)
            files.append(f"{solution.settings.get().projects[name]}/{path}")
    return files


def set_pch(root: Path, project: str, *, enable: bool) -> str | None:
    """PCHを有効にする（include/<Project>/pch.h をテンプレートから作る）か、外す。PCHのパスを返す。"""
    solution = open_solution(root)
    _require_project(solution, project)
    target = solution.get_project(project)
    message = f"Project {project} のPCHを設定できません。"
    try:
        with _transaction(solution, message):
            if not enable:
                target.settings.clear_pch()
                return None
            _ensure_templates(solution)
            header = f"include/{project}/pch.h"
            if not (target.root / header).exists():
                target.add_file(header, template_name="pch", auto_update=False)
            target.settings.set_pch(project_headers=[header])
            return f"{project}/{header}"
    except EcoBuildError:
        raise
    except Exception as error:
        raise _cppbuild_error(message, error) from error


# ファイル ---------------------------------------------------------------------

def project_root(root: Path, project: str) -> Path:
    solution = open_solution(root)
    _require_project(solution, project)
    return Path(solution.get_project(project).root)


def source_directories(root: Path, project: str) -> tuple[str, ...]:
    """Projectのソースフォルダー（Projectからの相対、既定は src・include）。この外のファイルはビルドに入らない。"""
    solution = open_solution(root)
    _require_project(solution, project)
    return tuple(solution.get_project(project).settings.get().source_directories)


def add_file(root: Path, project: str, path: str, *, replacements: dict | None = None,
             template: str | None = None) -> str:
    """Projectにファイルを足す（拡張子でテンプレートを選ぶ）。モジュールからの相対パスを返す。"""
    solution = open_solution(root)
    _require_project(solution, project)
    target = solution.get_project(project)
    suffix = Path(path).suffix.lower()
    if template is None:
        template = "header" if suffix in HEADER_SUFFIXES else "source" if suffix in SOURCE_SUFFIXES else None
    if template == "header":
        replacements = None  # ヘッダーのテンプレートには差し込む値がない（CppBuildは過不足を拒否する）
    if template == "source" and not (replacements or {}).get("header"):
        template = None      # 読み込むヘッダーがない（ライブラリをリンクしていない実行ファイル等）：空のファイル
    try:
        _ensure_templates(solution)
        if template is None:
            target.add_file(path, content="", auto_update=False)
        else:
            target.add_file(path, template_name=template, replacements=replacements, auto_update=False)
        solution.update()
    except FileExistsError:
        raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{path} は既に存在します。") from None
    except Exception as error:
        raise _cppbuild_error(f"{path} を追加できません。", error) from error
    return (Path(target.root) / path).relative_to(root).as_posix()


def remove_file(root: Path, project: str, path: str) -> str:
    solution = open_solution(root)
    target = solution.get_project(project)
    try:
        target.remove_file(path, auto_update=False)
        solution.update()
    except FileNotFoundError:
        raise EcoBuildError(ErrorCode.FILE_NOT_FOUND, f"{path} がありません。") from None
    except Exception as error:
        raise _cppbuild_error(f"{path} を削除できません。", error) from error
    return (Path(target.root) / path).relative_to(root).as_posix()


def move_files(root: Path, moves: list[tuple[str, str, str]]) -> tuple[str, ...]:
    """まとめて移動する（(Project, 元, 先)。構成の作り直しは最後に1回）。移動元・移動先の組を順に返す。"""
    solution = open_solution(root)
    done = []
    try:
        for project, source, destination in moves:
            target = solution.get_project(project)
            target.move_file(source, destination, auto_update=False)
            base = Path(target.root)
            done += [(base / source).relative_to(root).as_posix(), (base / destination).relative_to(root).as_posix()]
    except FileNotFoundError as error:
        raise EcoBuildError(ErrorCode.FILE_NOT_FOUND, f"{error} がありません。") from None
    except FileExistsError as error:
        raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{error} は既に存在します。") from None
    except Exception as error:
        raise _cppbuild_error("ファイルを移動できません。", error) from error
    finally:
        if done:
            solution.update()
    return tuple(done)


def remove_files(root: Path, removals: list[tuple[str, str]]) -> tuple[str, ...]:
    """まとめて削除する（(Project, パス)。構成の作り直しは最後に1回）。"""
    solution = open_solution(root)
    done = []
    try:
        for project, path in removals:
            target = solution.get_project(project)
            target.remove_file(path, auto_update=False)
            done.append((Path(target.root) / path).relative_to(root).as_posix())
    except FileNotFoundError as error:
        raise EcoBuildError(ErrorCode.FILE_NOT_FOUND, f"{error} がありません。") from None
    except Exception as error:
        raise _cppbuild_error("ファイルを削除できません。", error) from error
    finally:
        if done:
            solution.update()
    return tuple(done)


def move_file(root: Path, project: str, source: str, destination: str) -> tuple[str, str]:
    solution = open_solution(root)
    target = solution.get_project(project)
    try:
        target.move_file(source, destination, auto_update=False)
        solution.update()
    except FileNotFoundError:
        raise EcoBuildError(ErrorCode.FILE_NOT_FOUND, f"{source} がありません。") from None
    except FileExistsError:
        raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{destination} は既に存在します。") from None
    except Exception as error:
        raise _cppbuild_error(f"{source} を移動できません。", error) from error
    base = Path(target.root)
    return (base / source).relative_to(root).as_posix(), (base / destination).relative_to(root).as_posix()


# 依存先 -----------------------------------------------------------------------

def git_sources(root: Path):
    """依存先（このSolutionが記録するもの）の状態（CppBuildのGitSourceStatus）。"""
    solution = open_solution(root)
    try:
        return tuple(s for s in solution.git_sources() if s.recorded_by is None)
    except Exception as error:
        raise _cppbuild_error("依存先を読み込めません。", error) from error


def all_git_sources(root: Path) -> tuple[tuple, ...]:
    """依存先すべて（依存先の依存先も）と、それを記録している依存先の名前（直接ならNone）の組。"""
    solution = open_solution(root)
    try:
        sources = tuple(solution.git_sources())
    except Exception as error:
        raise _cppbuild_error("依存先を読み込めません。", error) from error

    def recorder(source) -> str | None:
        if source.recorded_by is None:
            return None
        by = Path(source.recorded_by).resolve()
        return next((s.name for s in sources if Path(s.directory).resolve() in (by, *by.parents)), None)

    return tuple((s, recorder(s)) for s in sources)


def dependency_graph(root: Path) -> tuple[tuple, dict[str, tuple[str, ...]]]:
    """依存先すべて（依存先の依存先も。CppBuildのGitSourceStatus）と、それぞれが直接記録する依存先の名前。

    手元にcloneがない依存先は、その先が分からないので空にする。
    """
    from cppbuild.git_sources import identity
    solution = open_solution(root)
    try:
        sources = tuple(solution.git_sources())
        names = {identity(s.url): s.name for s in sources}
        edges = {}
        for source in sources:
            records = Solution.open(source.config).settings.get().git_sources if source.present else {}
            edges[source.name] = tuple(sorted(names[identity(r.url)] for r in records.values()
                                              if identity(r.url) in names))
    except Exception as error:
        raise _cppbuild_error("依存先を読み込めません。", error) from error
    return sources, edges


def link(root: Path, project: str, url: str, *, shared: bool) -> str:
    """Projectから、gitのリポジトリにあるモジュールのライブラリをリンクする。依存先の名前を返す。"""
    solution = open_solution(root)
    _require_project(solution, project)
    before = {s.name for s in solution.git_sources()}
    message = f"{url} をリンクできません。"
    try:
        # 失敗したら、記録も、今cloneした相手も元に戻る（CppBuildのトランザクション）。_clone_config は外側に：
        # トランザクションの終わりの構成でも、依存先の依存先を clone する。
        with _clone_config(), _transaction(solution, message):
            solution.get_project(project).settings.link_git(
                url, solution_path=CONFIG_DIRECTORY, link_type=ProjectType.SHARED_LIBRARY if shared else ProjectType.STATIC_LIBRARY)
    except EcoBuildError:
        raise
    except AlreadyRegisteredError as error:
        raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{url} は既にリンクしています。") from error
    except NoMainProjectError as error:
        raise EcoBuildError(ErrorCode.NOT_LINKABLE, f"{url} のモジュールは、リンクできる形になっていません。",
                            hint="他のモジュールからリンクされるのは、そのモジュールで最初に作ったProject（main）"
                                 "だけで、それがライブラリである必要があります。",
                            details=str(error)) from error
    except Exception as error:
        raise _cppbuild_error(message, error) from error
    _write_clone_config(Path(s.directory) for s in solution.git_sources() if s.name not in before)
    added = [s.name for s in solution.git_sources() if s.name not in before]
    return added[0] if added else next(s.name for s in solution.git_sources() if s.url == url)


def unlink(root: Path, name: str) -> tuple[str, ...]:
    """依存先のリンクを、すべてのProjectから外し、記録を消す。外したProjectを返す。"""
    solution = open_solution(root)
    if not any(s.name == name and s.recorded_by is None for s in solution.git_sources()):
        raise EcoBuildError(ErrorCode.DEPENDENCY_NOT_FOUND, f"依存先 {name} はありません。")
    message = f"依存先 {name} を外せません。"
    try:
        with _transaction(solution, message):
            report = solution.unlink_git_source(name)   # すべてのProjectからのリンクと、記録（cloneは残る）
    except EcoBuildError:
        raise
    except Exception as error:
        raise _cppbuild_error(message, error) from error
    return tuple(project for project, _ in report.unlinked)


def record_latest(root: Path, name: str) -> str:
    """依存先の記録を、GitHubの既定ブランチの最新にする。記録したコミットを返す。"""
    solution = open_solution(root)
    source = next((s for s in solution.git_sources() if s.name == name and s.recorded_by is None), None)
    if source is None:
        raise EcoBuildError(ErrorCode.DEPENDENCY_NOT_FOUND, f"依存先 {name} はありません。")
    try:
        with _clone_config():
            revision = solution.set_git_source(source.url).revision
        _write_clone_config(Path(s.directory) for s in solution.git_sources())
        return revision
    except Exception as error:
        raise _cppbuild_error(f"依存先 {name} の最新を取得できません。", error) from error


# 内部 ----------------------------------------------------------------------

def _require_project(solution: Solution, project: str) -> None:
    projects = solution.settings.get().projects
    if project not in projects:
        raise EcoBuildError(ErrorCode.PROJECT_NOT_FOUND, f"Project {project} はありません。",
                            hint=f"モジュールのProject：{'、'.join(projects)}")


def _guid_names(solution: Solution) -> dict[str, str]:
    return {solution.get_project(name).settings.get().guid: name for name in solution.settings.get().projects}


def _add_library_header(project, path: str) -> None:
    """ライブラリの見出しのヘッダー。共有ライブラリ（DLL）にしてもソースを変えずに使えるよう、
    Windowsですべての関数を書き出す（CppBuildの windows_export_all_symbols。変数は書き出されない）。
    """
    project.add_file(path, template_name="header", auto_update=False)
    project.settings.set_windows_export_all_symbols()


def _ensure_templates(solution: Solution) -> None:
    """後から増えたテンプレート（bench等）を、古いモジュールにも登録する。"""
    existing = set(solution.settings.get().file_templates)
    missing = {name: file_name for name, file_name in TEMPLATES.items() if name not in existing}
    if missing:
        _register_templates(solution, missing)

def _ensure_solution_folders(solution: Solution) -> None:
    """Visual Studio のソリューションで、Projectをソリューションフォルダーに分ける（CppBuildの既定の名前：
    自分のProjectは Projects、リンク先は LinkedProjects/<Solution名>）。フォルダーなしで作った古いモジュールにも入れる。"""
    data = solution.settings.get()
    if data.solution_folders is None:
        data.solution_folders = SolutionFolderSettings()
        solution.settings.save(data)


def _register_templates(solution: Solution, templates: dict[str, str] = TEMPLATES) -> None:
    materials = resources.files("ecobuild_cpp") / "templates"
    for name, file_name in templates.items():
        # CppBuildは素材をSolutionの中から読み込むので、いったんSolutionの中へ置く。
        staging = solution.root / f".ecobuild-template-{file_name}"
        staging.write_bytes((materials / file_name).read_bytes())
        try:
            solution.create_file_template(name, staging.name)
        finally:
            staging.unlink()


def _solution_settings(**values) -> SolutionBuildSettings:
    return SolutionBuildSettings(intermediate_directory=f"{_TO_ROOT}/{BUILD_DIRECTORY}", **values)


def _target(root: Path, project: str | None, options: BuildOptions, *, run_arguments=None):
    solution = open_solution(root)
    configuration = options.configuration
    if configuration not in CONFIGURATIONS:
        raise EcoBuildError(ErrorCode.INVALID_CONFIGURATION, f"構成 {configuration} はありません。",
                            hint=f"{'・'.join(CONFIGURATIONS)} のどれかを指定してください。")
    projects = solution.settings.get().projects
    if project is not None and project not in projects:
        raise EcoBuildError(ErrorCode.PROJECT_NOT_FOUND, f"Project {project} はありません。",
                            hint=f"モジュールのProject：{'、'.join(projects)}")
    _apply_options(solution, options, run_project=project, run_arguments=run_arguments)
    if options.fetch_git:
        _fetch_missing(solution)
    return solution if project is None else solution.get_project(project)


@contextmanager
def _clone_config():
    """CppBuild が依存先を clone・取り出す間、git に ECOBuild の clone と同じ設定（ecowork の CLONE_CONFIG。改行コードを
    core.autocrlf=input に）を効かせる。CppBuild は git をこのプロセスの環境で動かすので、環境変数（GIT_CONFIG_COUNT・
    GIT_CONFIG_KEY_<n>・GIT_CONFIG_VALUE_<n>）で、今ある設定の後ろに足す。終われば元に戻す。

    付けないと Windows では CRLF で取り出し、コンテナ（Linux）の git から全ファイルが変更ありに見える。"""
    try:
        count = int(os.environ.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        count = 0
    values = {"GIT_CONFIG_COUNT": str(count + len(CLONE_CONFIG))}
    for index, setting in enumerate(CLONE_CONFIG, count):
        values[f"GIT_CONFIG_KEY_{index}"], values[f"GIT_CONFIG_VALUE_{index}"] = setting.split("=", 1)
    saved = {name: os.environ.get(name) for name in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _write_clone_config(directories) -> None:
    """依存先の clone の設定（--local）に CLONE_CONFIG を書く（後の取り出し・切り替え・コンテナの中の git でも効くように）。
    clone がない・書けないものは飛ばす（ビルド等を止めない）。"""
    for directory in directories:
        if not (directory / ".git").exists():
            continue
        git = Git(directory)
        for setting in CLONE_CONFIG:
            key, value = setting.split("=", 1)
            if git.get_config(key) != value:
                git.run("config", "--local", key, value, check=False)


def _fetch_missing(solution: Solution) -> None:
    """足りない依存先があれば、操作（構成・ビルド等。CppBuild がその前に clone する）より先に _clone_config の下で
    clone する。失敗したら何もしない（操作の側が clone し直し、いつもどおりに誤りを出す）。"""
    try:
        if all(s.present for s in solution.git_sources()):
            return
        with _clone_config():
            report = solution.fetch_git_sources()
        _write_clone_config(Path(s.directory) for s in report.sources if s.name in report.fetched)
    except Exception:
        pass


def _apply_options(solution: Solution, options: BuildOptions, *, run_project: str | None = None,
                   run_arguments=None) -> None:
    """ビルド設定をSolutionと各Projectに渡す（CppBuildは保存しないので、開くたびに渡す）。

    構成・生成環境はSolution全体で1つ（依存でつながるProjectは揃っている必要がある）。Projectごとに変えられるのは
    ライブラリの形式・C++の規格・成果物の置き場所・テストの並列数・GoogleTestのZIP。
    """
    overrides = dict(options.projects)
    names = solution.settings.get().projects
    unknown = [name for name in overrides if name not in names]
    if unknown:
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"ビルド設定に、ない Project {'、'.join(unknown)} の設定があります。",
                            hint=f"{operation(options.command, 'profile add')} で、その Project の設定を外してください（--clear-project）。")
    for name, own in overrides.items():
        if own.type and LIBRARY_TYPES[own.type] not in solution.get_project(name).settings.get().types:
            raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"ビルド設定で、ライブラリでない Project {name} の形式を変えています。",
                                hint="形式（type）を変えられるのはライブラリだけです。")
    try:
        # 構成（Debug／Release）はSolution全体で1つ。Projectは対象を絞るだけで、構成は引き継ぐ。
        # shared：依存先も含め、ライブラリを共有ライブラリにする（Projectの形式の指定が優先）。
        solution.set_build_settings(_solution_settings(
            configuration=options.configuration, parallel=options.parallel, shared_libraries=options.shared,
            architecture=options.architecture, cpp_standard=options.cpp_standard or 20,
            test_continue_on_failure=options.test_continue_on_failure, fetch_git=options.fetch_git,
            tools=ToolSettings(cmake=options.cmake or "cmake", ctest=options.ctest or "ctest"),
            cmake=CMakeSettings(generator=options.generator, toolset=options.toolset, c_compiler=options.c_compiler,
                                cxx_compiler=options.cxx_compiler, toolchain_file=options.toolchain_file,
                                windows_sdk=options.windows_sdk)))
        for name in names:
            own = overrides.get(name, ProjectOptions())
            settings = ProjectBuildSettings(
                parallel=options.parallel,
                project_type=LIBRARY_TYPES[own.type] if own.type else None,
                cpp_standard=own.cpp_standard or INHERIT,
                artifact_directory=own.artifact_directory,
                test_parallel=own.test_parallel or options.test_parallel,
                googletest_archive=own.googletest_archive or options.googletest_archive)
            if name == run_project and run_arguments is not None:
                settings.run_arguments = list(run_arguments)
            solution.get_project(name).set_build_settings(settings)
    except Exception as error:
        raise _cppbuild_error("ビルド設定を渡せません。", error) from error


def _tests(solution: Solution) -> list[str]:
    return [name for name in solution.settings.get().projects
            if ProjectType.TEST in solution.get_project(name).settings.get().types]


def linked_libraries(root: Path, project: str) -> list[str]:
    """Projectがリンクしている、同じモジュールのライブラリ。"""
    solution = open_solution(root)
    _require_project(solution, project)
    by_guid = _guid_names(solution)
    names = [by_guid[d.project_guid] for d in solution.get_project(project).settings.get().dependencies.values()
             if getattr(d, "project_guid", None) in by_guid]
    return [n for n in names if ProjectType.STATIC_LIBRARY in solution.get_project(n).settings.get().types]


def is_test_project(root: Path, project: str) -> bool:
    solution = open_solution(root)
    return project in _tests(solution)


def _executables(solution: Solution) -> list[str]:
    return [name for name in solution.settings.get().projects
            if ProjectType.EXECUTABLE in solution.get_project(name).settings.get().types]


def _single_executable(solution: Solution) -> str:
    executables = _executables(solution)
    if len(executables) != 1:
        raise EcoBuildError(
            ErrorCode.RUN_FAILED,
            "実行するProjectを決められません。" if executables else "実行ファイルのProjectがありません。",
            hint="実行するProjectの名前を指定してください。" if executables else None,
            details=executables,
        )
    return executables[0]


def _process(report) -> ProcessOutput:
    return ProcessOutput(" ".join(report.command), report.returncode, report.output)


def _joined(processes) -> str:
    return "\n".join(p.output for p in processes if p.output)


def _cppbuild_error(message: str, error: Exception) -> EcoBuildError:
    """CppBuildの例外を、ECOBuildのエラーにする（CppBuildの例外の型で決める。文面は見ない）。"""
    details = f"{type(error).__name__}: {error}"
    if isinstance(error, AlreadyRegisteredError):
        return EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{message}（{error.name} は既にあります）", details=details)
    if isinstance(error, NotRegisteredError):
        code = {"project": ErrorCode.PROJECT_NOT_FOUND, "git_source": ErrorCode.DEPENDENCY_NOT_FOUND,
                "dependency": ErrorCode.DEPENDENCY_NOT_FOUND}.get(error.kind)
        if code is not None:
            return EcoBuildError(code, f"{message}（{error.name} はありません）", details=details)
    if isinstance(error, InvalidValueError):
        hint = f"{error.field} に指定できるのは {'・'.join(map(str, error.allowed))} です。" if error.allowed else None
        return EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{message}（{error.field} の値 {error.value!r} は使えません）",
                             hint=hint, details=details)
    return EcoBuildError(ErrorCode.CPPBUILD_ERROR, message, details=details)


@contextmanager
def _transaction(solution: Solution, message: str):
    """設定の変更と、それを反映する更新（生成ファイルの作り直しとCMakeの構成）を一体にする。

    中で例外が起きるか、更新に失敗したら、書いた管理ファイル・生成ファイルと、今cloneした依存先を元に戻す
    （CppBuildの Solution.transaction）。ソースファイルとビルドツリーは戻さない。更新の失敗は EcoBuildError にする。
    """
    with solution.transaction() as report:
        yield report
    if not report.success:
        update = report.update
        processes = update.processes if hasattr(update, "processes") else (update.process,)
        raise EcoBuildError(ErrorCode.CPPBUILD_ERROR, f"{message}CMakeの構成に失敗したので、設定を元に戻しました。",
                            hint="パス・ターゲット名等を確かめてください（詳細はCMakeの出力）。",
                            details=_joined(tuple(_process(p) for p in processes)))
