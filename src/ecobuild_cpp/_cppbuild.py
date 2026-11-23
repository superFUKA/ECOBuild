"""CppBuild の呼び出し（cpp 型の内部）。"""

from __future__ import annotations

import hashlib
import os
import re
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
                      CMakeSettings, GitFetchError, InvalidValueError, NoMainSubprojectError, NotRegisteredError, SubprojectBuildSettings,
                      SubprojectType, Solution, SolutionBuildSettings, SolutionFolderSettings, ToolSettings)

from cppbuild import engine as _engine
from cppbuild.models import LIBRARY_TYPES as _LINKABLE_TYPES
from cppbuild import execution as _execution
from cppbuild import logs as _logs
from cppbuild import workspace as _workspace

from ecowork.git import CLONE_CONFIG, Git

from ecobuild.config import DIRECTORY
from ecobuild.errors import EcoBuildError, operation

from .errors import ErrorCode
from . import _migrate
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
    "library": SubprojectType.STATIC_LIBRARY,
    "shared": SubprojectType.SHARED_LIBRARY,
    "app": SubprojectType.EXECUTABLE,
    "test": SubprojectType.TEST,
    "bench": SubprojectType.EXECUTABLE,
}
# 種類のうちライブラリ（組のテスト用Projectを作る・--link は使えない）
LIBRARY_KINDS = ("library", "shared")
# project set --kind で変えられる種類（テスト用・性能測定は、リンクするライブラリが決まらないので除く）
CHANGEABLE_KINDS = ("app", "library", "shared")
# ライブラリの形式（project set --for・project link --as・ビルド設定の type）→ CppBuildの種類
LIBRARY_TYPES = {
    "static": SubprojectType.STATIC_LIBRARY,
    "shared": SubprojectType.SHARED_LIBRARY,
    "interface": SubprojectType.INTERFACE_LIBRARY,
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
    if _migrate.is_old(root / CONFIG_DIRECTORY):
        raise old_format_error()
    try:
        solution = Solution.open(root / CONFIG_DIRECTORY)
        solution.set_build_settings(_solution_settings())
        return solution
    except Exception as error:  # CppBuildの例外は種類が多いので、まとめて変換する
        raise _cppbuild_error("CppBuildのSolutionを開けません。", error) from error


def old_format_error() -> EcoBuildError:
    return EcoBuildError(ErrorCode.OLD_FORMAT,
                         f"このモジュールの CppBuild の管理ファイル（{CONFIG_DIRECTORY}）は古い形式です（今の CppBuild では読めません）。",
                         hint="ecobuild module upgrade で新しい形式にしてください（タスクブランチで実行し、提出してください）。")


def old_dependencies(solution: Solution) -> tuple[str, ...]:
    """手元の clone（依存先の依存先も）のうち、CppBuild の管理ファイルが古い形式のものの名前。

    CppBuild は古い形式の clone を「ない」とみなし、その先（依存先の依存先）もたどらない。古い形式を新しくすれば
    その先も見える。"""
    try:
        sources = solution.git_sources()
    except Exception:   # 記録の食い違い等は、操作の側がいつもどおりに誤りを出す
        return ()
    return tuple(s.name for s in sources if not s.present and _migrate.is_old(Path(s.directory) / s.path))


def check_dependency_formats(solution: Solution) -> None:
    """依存先に古い形式の clone があれば止める（CppBuild の英語の誤りの代わりに、どれをどうするかを示す）。

    案内は場合で分ける：手元の clone が記録の版と違う（他の人が記録を進めたのを取り込んだ後など）なら deps sync、
    直接の依存先の記録の版が古い形式なら、その依存先を新しくして deps update、依存先の依存先なら、それを記録している
    直接の依存先を新しくする（deps update が受けるのは直接の記録だけ）。"""
    old = old_dependencies(solution)
    if not old:
        return
    sources = {s.name: s for s in solution.git_sources()}
    advice = [_old_format_advice(sources[name], sources) for name in old]
    raise EcoBuildError(
        ErrorCode.DEPENDENCY_OLD_FORMAT,
        f"依存先 {'、'.join(old)} の CppBuild の管理ファイルが古い形式です（手元の clone が古いコミットです）。",
        hint="\n".join(advice), details=[f"{DEPENDENCY_DIRECTORY}/{name}" for name in old])


def _old_format_advice(source, sources: dict) -> str:
    name = source.name
    head = Git(Path(source.directory)).run("rev-parse", "HEAD", check=False)
    if head.ok and head.stdout.strip() != source.revision:
        return (f"{name}：手元の clone が記録の版と違います。まず ecobuild deps sync で記録の版にしてください"
                f"（記録の版が新しい形式なら、それで直ります）。")
    if source.recorded_by is None:
        return (f"{name}：記録の版が古い形式です。{name} のモジュールで ecobuild module upgrade をして取り込んでから、"
                f"このモジュールで ecobuild deps update {name} を実行してください。")
    chain = _recorders(source, sources)   # 記録している依存先（近い順。最後が直接の依存先）
    steps = [f"{name} のモジュールで ecobuild module upgrade"]
    below = name
    for recorder in chain:
        steps.append(f"{recorder} のモジュールで ecobuild deps update {below}")
        below = recorder
    direct = chain[-1] if chain else "<直接の依存先>"
    return (f"{name}：依存先 {chain[0] if chain else direct} が、{name} の古い形式の版を記録しています。"
            + "、".join(steps) + f" をして、それぞれ取り込んでから、このモジュールで ecobuild deps update {direct} を実行してください。")


def _recorders(source, sources: dict) -> list[str]:
    """依存先の依存先 source を記録している依存先の名前を、近い順に直接の依存先までたどる。"""
    result, current = [], source
    while current.recorded_by is not None and len(result) < len(sources):
        by = Path(current.recorded_by).resolve()
        found = next((s for s in sources.values() if s.name not in result
                      and Path(s.directory).resolve() in (by, *by.parents)), None)
        if found is None:
            break
        result.append(found.name)
        current = found
    return result


def create_module_solution(root: Path, name: str, kind: str, project: str | None = None, *,
                           test: bool = True) -> Solution:
    """Solutionと、最初のProjectを作る（生成はしない）。kind：app＝実行ファイル <Project名>、
    library＝静的ライブラリ <Project名> とテスト用 <Project名>Test（test が偽なら作らない）、shared＝同じく共有ライブラリ、
    none＝Projectを作らない。
    Project名は project（省略時はモジュール名）。

    CppBuildは最初に作ったProjectを main_subproject にし、他のモジュールからリンクされるのはそれだけ
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
    project = solution.add_subproject(name, name, PROJECT_KINDS[kind])
    header = library_header(name)
    _add_library_header(project, f"include/{header}")
    project.add_file(f"src/{name}.cpp", template_name="source", replacements={"header": header}, auto_update=False)
    files = [f"{name}/include/{header}", f"{name}/src/{name}.cpp"]
    if test:
        files += _create_linked(solution, test_project_of(name), "test", name, suite=name)
    return files


def _create_linked(solution: Solution, name: str, kind: str, library: str | None, *, suite: str | None = None) -> list[str]:
    """実行ファイル・テスト・性能測定のProject。library があればリンクし、そのヘッダーを読み込む素材を置く。"""
    project = solution.add_subproject(name, name, PROJECT_KINDS[kind])
    if library is None:   # app だけ（test・bench はライブラリが要る）
        project.add_file("src/main.cpp", template_name="app", auto_update=False)
        return [f"{name}/src/main.cpp"]
    other = solution.get_subproject(library)   # ライブラリの作成時の形式（静的・共有）でリンクする
    project.settings.link_subproject(other, other.settings.get().initial_type)
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
    check_dependency_formats(solution)
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


def test(root: Path, *, project: str | None, options: BuildOptions, tests: tuple[str, ...] = ()) -> TestOutcome:
    """テスト用のProjectがなければ、何もせずに成功（ケースなし）。

    tests：流すテスト。<テスト用Project>（その全部）か <テスト用Project>.<Suite>.<Test>（* は任意の文字列、? は1文字）。
    project がテスト用Projectなら、その中の <Suite>.<Test> だけでもよい。ケースの名前は <テスト用Project>.<Suite>.<Test>
    （そのまま並べて流し直せる）。"""
    solution = open_solution(root)
    if project is None and not tests and not _tests(solution):
        return TestOutcome(True, (), ())
    selection = _test_selection(solution, project, tests) if tests else None
    target = _target(root, None if selection else project, options, test_selection=selection)
    try:
        report = target.test()
    except Exception as error:
        raise _cppbuild_error("テストを実行できません。", error) from error
    reports = report.subprojects if report.subprojects else (report,)
    cases = tuple(TestCase(f"{r.subproject}.{c.name}" if r.subproject else c.name, c.status) for r in reports for c in r.cases)
    processes = tuple(_process(p) for r in reports for p in r.processes)
    diagnostics = tuple(d for r in reports for d in r.diagnostics)
    outcome = TestOutcome(report.success, cases, processes, diagnostics)
    if not outcome.success:
        failed = [c.name for c in cases if c.status not in {"passed", "skipped"}]
        unmatched = [r.subproject for r in reports if any(d.startswith("No tests match") for d in r.diagnostics)]
        message = ("テストに失敗しました。" + (f"（{', '.join(failed)}）" if failed else "") if failed or not unmatched
                   else f"当てはまるテストがありません（{'、'.join(unmatched)}）。")
        raise EcoBuildError(ErrorCode.TEST_FAILED, message,
                            hint=None if failed or not unmatched else
                            "名前は <テスト用Project>.<Suite>.<Test> です（* ? が使えます。ecobuild test で全部の名前が出ます）。",
                            details={"cases": [c.__dict__ for c in cases], "diagnostics": list(diagnostics),
                                     "output": _joined(processes)})
    return outcome


def _test_selection(solution: Solution, project: str | None, tests: tuple[str, ...]) -> dict[str, list[str] | None]:
    """流すテスト（test の tests）を、テスト用Projectごとのケースのパターンに（None はその全部）。"""
    names = _tests(solution)
    if project is not None and project not in names:
        raise EcoBuildError(ErrorCode.PROJECT_NOT_FOUND, f"Project {project} はテスト用ではありません。",
                            hint=f"テスト用のProject：{'、'.join(names) or 'なし'}")
    selection: dict[str, list[str] | None] = {}
    for test in tests:
        # Project名に . があってもよいので、長い名前から当てる
        owner = next((n for n in sorted(names, key=len, reverse=True) if test == n or test.startswith(n + ".")), None)
        if owner is None and project is None:
            raise EcoBuildError(ErrorCode.PROJECT_NOT_FOUND, f"テスト {test} のテスト用Projectが分かりません。",
                                hint=f"<テスト用Project>.<Suite>.<Test> で書いてください（テスト用のProject："
                                     f"{'、'.join(names) or 'なし'}）。")
        if owner is None or (project is not None and owner != project):
            owner, pattern = project, test
        else:
            pattern = test[len(owner) + 1:] if test != owner else None
        if pattern is None or selection.get(owner, []) is None:
            selection[owner] = None
        else:
            selection.setdefault(owner, []).append(pattern)
    return selection


# GoogleTest のテストの書き方。TEST・TEST_F はそのままの名前、値・型でふやすものは CTest の名前に合うパターン
# （TEST_P：<Prefix>/<Suite>.<Test>/<番号>、TYPED_TEST：<Suite>/<番号>.<Test>、TYPED_TEST_P：<Prefix>/<Suite>/<番号>.<Test>）。
_TEST_MACRO = re.compile(r"^[ \t]*(TEST|TEST_F|TEST_P|TYPED_TEST|TYPED_TEST_P)[ \t]*\([ \t]*(\w+)[ \t]*,[ \t]*(\w+)[ \t]*\)", re.M)
_TEST_NAMES = {"TEST": "{suite}.{test}", "TEST_F": "{suite}.{test}", "TEST_P": "*/{suite}.{test}/*",
               "TYPED_TEST": "{suite}/*.{test}", "TYPED_TEST_P": "*/{suite}/*.{test}"}


def list_tests(root: Path, *, project: str | None) -> list[tuple[str, str, int]]:
    """テスト用Projectのソースに書いてあるテスト（名前・モジュールからの相対のファイル・行）。ビルドしない。

    名前は test の tests に渡せる <テスト用Project>.<Suite>.<Test>（値・型でふやすテストはパターン）。
    project：そのテスト用Projectだけ（テスト用でなければ PROJECT_NOT_FOUND）。"""
    solution = open_solution(root)
    names = _tests(solution)
    if project is not None and project not in names:
        raise EcoBuildError(ErrorCode.PROJECT_NOT_FOUND, f"Project {project} はテスト用ではありません。",
                            hint=f"テスト用のProject：{'、'.join(names) or 'なし'}")
    found = []
    for name in [project] if project else names:
        base = Path(solution.get_subproject(name).root)
        for directory in solution.get_subproject(name).settings.get().source_directories:
            for path in sorted((base / directory).rglob("*")):
                if path.suffix.lower() not in SOURCE_SUFFIXES + HEADER_SUFFIXES or not path.is_file():
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                relative = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()
                for match in _TEST_MACRO.finditer(text):
                    macro, suite, test = match.groups()
                    found.append((f"{name}." + _TEST_NAMES[macro].format(suite=suite, test=test), relative,
                                  text.count("\n", 0, match.start()) + 1))
    return list(dict.fromkeys(found))


def run(root: Path, *, project: str | None, options: BuildOptions, arguments: str) -> BuildOutcome:
    solution = open_solution(root)
    name = project or _single_executable(solution)
    if (project is not None and project in solution.settings.get().subprojects
            and SubprojectType.EXECUTABLE not in solution.get_subproject(project).settings.get().types):
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
def program_output(write: Callable[..., None], *, tools: bool = True) -> Iterator[None]:
    """この中で CppBuild が動かす子プロセスの出力を、1行ずつ write(行, stream, source) に渡す（行は改行なし。stream：
    stdout・stderr、source：program〔実行するプログラム〕・tool〔CMake・コンパイラー・CTest 等〕。結果の output は
    今までどおり全部〔stdout と stderr を届いた順に〕）。tools：ツールの出力も渡す。偽なら、実行するプログラムの出力だけ。

    CppBuild には出力を逐次受け取る口がない（子プロセスはどれも cppbuild.engine.process で、stderr を stdout にまとめて
    終わるまでためる）ので、その間だけ、同じ形の結果（ProcessReport）を返す、stdout・stderr を分けて読みながら渡すものに
    替える。実行するプログラムは cppbuild.execution.execute に渡されるコマンドで見分ける。CppBuild に口ができたら、それに替える。
    """
    original, original_execute, lock = _engine.process, _execution.execute, threading.Lock()
    programs: set[tuple[str, ...]] = set()

    def execute(commands, *args, **kwargs):
        commands = list(commands)
        programs.update(tuple(str(arg) for arg in command) for command, _cwd, _env in commands)
        return original_execute(commands, *args, **kwargs)

    def process(command, cwd, env=None):
        command = tuple(str(arg) for arg in command)
        source = "program" if command in programs else "tool"
        if not tools and source == "tool":
            return original(command, cwd, env)
        with _logs.command(command, cwd, env) as finished:
            child = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
                                     env=dict(os.environ) if env is None else env)
            data: list[bytes] = []

            def read(pipe, stream: str) -> None:
                with pipe:
                    for line in pipe:
                        with lock:   # 並べて動かす実行（run_parallel）と stdout・stderr の行が混ざらないように
                            data.append(line)
                            for text in _engine.decode_output(line).rstrip("\n").split("\n"):
                                write(text, stream, source)

            readers = [threading.Thread(target=read, args=(child.stdout, "stdout"), daemon=True),
                       threading.Thread(target=read, args=(child.stderr, "stderr"), daemon=True)]
            for reader in readers:
                reader.start()
            for reader in readers:
                reader.join()
            returncode = child.wait()
            output = _engine.decode_output(b"".join(data))
            finished(returncode, output)
        return _engine.ProcessReport(command, returncode, output)

    _engine.process, _execution.execute = process, execute
    try:
        yield
    finally:
        _engine.process, _execution.execute = original, original_execute


@dataclass(frozen=True)
class DependencySource:
    name: str
    directory: Path
    revision: str           # 記録されたコミット
    present: bool


def fetch_dependencies(root: Path) -> tuple[tuple[str, ...], tuple[DependencySource, ...]]:
    """足りない依存先を記録の版でcloneし、（今回cloneした名前, 全依存先）を返す。

    古い形式の clone（old_dependencies）があれば clone はしない（CppBuild は置き場所があるので断る）。それも依存先に
    含めて返すので、記録の版に切り替えられる（記録が新しい形式の版なら、それで新しくなる）。"""
    solution = open_solution(root)
    old = old_dependencies(solution)
    if old:
        sources = tuple(DependencySource(s.name, Path(s.directory), s.revision, True) for s in solution.git_sources()
                        if s.present or s.name in old)
        return (), sources
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
    for name in solution.settings.get().subprojects:
        directory = Path(solution.get_subproject(name).root).resolve()
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
    for name, directory in solution.settings.get().subprojects.items():
        data = solution.get_subproject(name).settings.get()
        links = tuple(by_guid.get(d.subproject_guid, d.subproject_guid) for d in data.dependencies.values()
                      if hasattr(d, "subproject_guid"))
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
    existing = solution.settings.get().subprojects
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
    libraries = [name for name in solution.settings.get().subprojects
                 if SubprojectType.STATIC_LIBRARY in solution.get_subproject(name).settings.get().types]
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

    main_subproject（他のモジュールからリンクされるもの）なら、先に main_subproject をなしにする（CppBuildは
    main_subproject のままでは外せない）。そうしたら True。
    """
    solution = open_solution(root)
    _require_project(solution, name)
    try:
        with _transaction(solution, f"Project {name} を外せません。"):
            data = solution.settings.get()
            was_main = data.main_subproject == name
            if was_main:
                data.main_subproject = None
                solution.settings.save(data)
            guid = solution.get_subproject(name).settings.get().guid
            for other in solution.subprojects():
                if other.name == name:
                    continue
                for key, dependency in list(other.settings.get().dependencies.items()):
                    if getattr(dependency, "subproject_guid", None) == guid:
                        other.settings.unlink(key)
            solution.remove_subproject(name)
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
    project = solution.get_subproject(name)
    data = project.settings.get()
    target = PROJECT_KINDS[kind]
    if data.initial_type == target:
        return ()
    if data.initial_type == SubprojectType.TEST:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{name} はテスト用のProjectなので、種類を変えられません。")
    module = solution.settings.get()
    library = data.initial_type in LIBRARY_TYPES.values()
    to_library = kind in LIBRARY_KINDS
    main = module.main_subproject
    is_main = main == name
    users = [(other, key, dependency) for other in solution.subprojects() if other.name != name
             for key, dependency in other.settings.get().dependencies.items()
             if getattr(dependency, "subproject_guid", None) == data.guid]
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
                                 f"先に {operation(command, 'module settings set')} --no-main で main をなしにしてください"
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
                if getattr(dependency, "subproject_guid", None) in references}
    fresh.dependencies = {key: value for key, value in data.dependencies.items() if key not in external}
    folders = module.solution_folders
    folder = None if folders is None else folders.subproject_folders.get(name)
    directory = module.subprojects[name]
    test_name = test_project_of(name)
    make_test = to_library and not library and test and test_name not in module.subprojects and not (root / test_name).exists()
    if make_test:
        check_project_name(test_name)
    message = f"Project {name} の種類を変えられません。"
    files: list[str] = []
    try:
        _ensure_templates(solution)
        with _transaction(solution, message):
            if is_main:
                module.main_subproject = None
                solution.settings.save(module)
            for other, key, _ in users:
                other.settings.unlink(key)
            solution.remove_subproject(name)
            remade = solution.add_subproject(directory, name, target, settings=fresh)
            for dependency in external.values():
                place = solution.root / references[dependency.subproject_guid].solution_directory
                remade.settings.link_solution(place, dependency.subproject_type)
            for other, _, dependency in users:   # 作成時の形式でリンクしていたものは、新しい形式で
                as_type = target if dependency.subproject_type == data.initial_type else dependency.subproject_type
                other.settings.link_subproject(remade, as_type)
            # main は元のとおりに（CppBuildは、Projectがほかにない Solution に足したProjectを main にする）。
            module = solution.settings.get()
            if module.main_subproject != main or folder is not None:
                module.main_subproject = main
                if folder is not None:
                    module.solution_folders.subproject_folders[name] = folder
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
            files.append(f"{solution.settings.get().subprojects[name]}/{path}")
    return files


def set_pch(root: Path, project: str, *, enable: bool) -> str | None:
    """PCHを有効にする（include/<Project>/pch.h をテンプレートから作る）か、外す。PCHのパスを返す。"""
    solution = open_solution(root)
    _require_project(solution, project)
    target = solution.get_subproject(project)
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
            target.settings.set_pch(subproject_headers=[header])
            return f"{project}/{header}"
    except EcoBuildError:
        raise
    except Exception as error:
        raise _cppbuild_error(message, error) from error


# ファイル ---------------------------------------------------------------------

def project_root(root: Path, project: str) -> Path:
    solution = open_solution(root)
    _require_project(solution, project)
    return Path(solution.get_subproject(project).root)


def source_directories(root: Path, project: str) -> tuple[str, ...]:
    """Projectのソースフォルダー（Projectからの相対、既定は src・include）。この外のファイルはビルドに入らない。"""
    solution = open_solution(root)
    _require_project(solution, project)
    return tuple(solution.get_subproject(project).settings.get().source_directories)


_batch = threading.local()   # one_update の中：作り直しを待っているモジュール（root）と、足したファイル


@contextmanager
def one_update(root: Path) -> Iterator[None]:
    """この中の add_file の構成の作り直し（cmake の構成）を、最後に1回にする（ヘッダーとそのテストを続けて足すと、
    1つ足すたびに構成を作り直していた）。途中で失敗しても、それまでに足したファイルの分は作り直す（1つずつのときと同じ）。"""
    if getattr(_batch, "root", None) is not None:   # 入れ子：外側がまとめて作り直す
        yield
        return
    _batch.root, _batch.paths = Path(root), []
    failed = interrupted = False
    try:
        yield
    except Exception:
        failed = True
        raise
    except BaseException:   # Ctrl+C 等：作り直しを待たせない（1つずつのときも、中断の後は作り直さない）
        interrupted = True
        raise
    finally:
        paths, _batch.root, _batch.paths = _batch.paths, None, []
        if paths and not interrupted:
            try:
                open_solution(root).update()
            except EcoBuildError:
                if not failed:   # 先の誤りがあれば、そちらを出す
                    raise
            except Exception as error:
                if not failed:   # 1つずつのときと同じ文（作り直しに失敗したのは、最初に足したファイルの後）
                    raise _cppbuild_error(f"{paths[0]} を追加できません。", error) from error


def _update_after_add(root: Path, solution, path: str) -> None:
    """add_file の後の構成の作り直し。one_update の中なら、最後に1回にまとめる。"""
    if getattr(_batch, "root", None) == Path(root):
        _batch.paths.append(path)
    else:
        solution.update()


def add_file(root: Path, project: str, path: str, *, replacements: dict | None = None,
             template: str | None = None) -> str:
    """Projectにファイルを足す（拡張子でテンプレートを選ぶ）。モジュールからの相対パスを返す。"""
    solution = open_solution(root)
    _require_project(solution, project)
    target = solution.get_subproject(project)
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
        _update_after_add(root, solution, path)
    except FileExistsError:
        raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{path} は既に存在します。") from None
    except Exception as error:
        raise _cppbuild_error(f"{path} を追加できません。", error) from error
    return (Path(target.root) / path).relative_to(root).as_posix()


def move_files(root: Path, moves: list[tuple[str, str, str]]) -> tuple[str, ...]:
    """まとめて移動する（(Project, 元, 先)。構成の作り直しは最後に1回）。移動元・移動先の組を順に返す。"""
    solution = open_solution(root)
    done = []
    try:
        for project, source, destination in moves:
            target = solution.get_subproject(project)
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
    """まとめて削除する（(Project, パス)。構成の作り直しは最後に1回）。

    削除と構成は一体：構成に失敗したら（Projectの最後の .cpp を消してソースがなくなった等）、管理ファイルは
    CppBuildの transaction が、消したファイルは消す前の中身から戻し、何も変えずにエラーにする。"""
    solution = open_solution(root)
    files = [(project, path, Path(solution.get_subproject(project).root) / path) for project, path in removals]
    for _, _, file in files:
        if not file.is_file():
            raise EcoBuildError(ErrorCode.FILE_NOT_FOUND, f"{file} がありません。")
    saved = {file: file.read_bytes() for _, _, file in files}
    message = "ファイルを削除できません。"
    try:
        with solution.transaction() as report:
            for project, path, _ in files:
                solution.get_subproject(project).remove_file(path, auto_update=False)
        if report.update.success:
            return tuple(file.relative_to(root).as_posix() for _, _, file in files)
        failure = EcoBuildError(ErrorCode.CPPBUILD_ERROR, f"{message}CMakeの構成に失敗したので、元に戻しました。",
                                details=_joined(tuple(_process(p) for p in report.update.processes)))
    except Exception as error:
        failure = _cppbuild_error(f"{message}構成に失敗したので、元に戻しました。", error)
    for file, content in saved.items():
        if not file.is_file():
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(content)
    sourceless = _without_sources(solution, files)
    if sourceless:
        failure = EcoBuildError(failure.code, f"{message}{'・'.join(sourceless)} のソース（.cpp 等）がなくなるので、元に戻しました。",
                                hint="C++のProjectには、コンパイルするソースが1つは要ります。先に別のソースを足すか、"
                                     "Projectごと消してください。", details=failure.details)
    raise failure


def _without_sources(solution: Solution, files: list[tuple[str, str, Path]]) -> list[str]:
    """消すとソース（コンパイルするファイル）が1つもなくなるProject（ヘッダーだけのライブラリは除く）。
    構成の失敗の説明に使うだけで、断るかどうかは CppBuild の構成が決める。"""
    gone = {file.resolve() for _, _, file in files}
    names = []
    for name in dict.fromkeys(project for project, _, _ in files):
        project = solution.get_subproject(name)
        settings = project.settings.get()
        if settings.initial_type == SubprojectType.INTERFACE_LIBRARY:
            continue
        root = Path(project.root)
        left = [p for directory in settings.source_directories if (root / directory).is_dir()
                for p in (root / directory).rglob("*") if p.is_file() and p.resolve() not in gone]
        if not any(p.suffix.lower() in (*SOURCE_SUFFIXES, ".c") for p in left):
            names.append(name)
    return names


def move_file(root: Path, project: str, source: str, destination: str) -> tuple[str, str]:
    solution = open_solution(root)
    target = solution.get_subproject(project)
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


def dependency_libraries_in_use(root: Path) -> dict[str, tuple[str, ...]]:
    """依存先の名前（依存先の依存先も）→ リンクされているライブラリ（このモジュールと、手元に clone のある依存先から）。"""
    solution = open_solution(root)
    try:
        sources = [s for s in solution.git_sources() if s.present]
        opened = {s.name: Solution.open(s.config) for s in sources}
        owner = {guid: (name, library) for name, other in opened.items() for guid, library in _guid_names(other).items()}
        result: dict[str, set[str]] = {}
        for own, each in ((None, solution), *opened.items()):
            for project in each.subprojects():
                for dependency in project.settings.get().dependencies.values():
                    found = owner.get(getattr(dependency, "subproject_guid", None))
                    # 依存先が自分の中でリンクしているもの（EngineTest → Engine 等）は、ほかから使われているのではない
                    if found is not None and found[0] != own:
                        result.setdefault(found[0], set()).add(found[1])
    except Exception as error:
        raise _cppbuild_error("依存先を読み込めません。", error) from error
    return {name: tuple(sorted(libraries)) for name, libraries in result.items()}


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


@dataclass(frozen=True)
class Library:
    """モジュール（Solution）の Project のうちの1つ（deps libraries・deps add --library で選ぶもの）。"""
    name: str
    kind: str          # 作成時の種類（static_library・executable 等）
    main: bool         # 既定でリンクされるもの（CppBuild の main_subproject）
    linkable: bool     # ライブラリ（リンクできる形がある）
    guid: str


def libraries_of(solution: Solution) -> tuple[Library, ...]:
    """Solution の Project の一覧（リンクできるものが先、その中は名前の順）。"""
    data = solution.settings.get()
    result = []
    for name in data.subprojects:
        values = solution.get_subproject(name).settings.get()
        result.append(Library(name, values.initial_type.value, name == data.main_subproject,
                              any(kind in _LINKABLE_TYPES for kind in values.types), values.guid))
    return tuple(sorted(result, key=lambda library: (not library.linkable, library.name)))


def dependency_libraries(root: Path, name: str) -> tuple[object, tuple[Library, ...]]:
    """依存先 name（依存先の依存先も）の (CppBuild の GitSourceStatus, ライブラリの一覧)。手元の clone から読む。"""
    solution = open_solution(root)
    source = next((s for s in solution.git_sources() if s.name == name), None)
    if source is None:
        raise EcoBuildError(ErrorCode.DEPENDENCY_NOT_FOUND, f"依存先 {name} はありません。")
    return source, _libraries_at(solution, source)


def _libraries_at(solution: Solution, source) -> tuple[Library, ...]:
    if _migrate.is_old(Path(source.directory) / source.path):
        check_dependency_formats(solution)   # 古い形式の clone：同じ案内で止める
    if not source.present:
        raise EcoBuildError(ErrorCode.DEPENDENCY_NOT_FOUND, f"依存先 {source.name} の clone がありません。",
                            hint="ecobuild deps sync で取得してから読めます。")
    try:
        return libraries_of(Solution.open(source.config))
    except Exception as error:
        raise _cppbuild_error(f"依存先 {source.name} を読み込めません。", error) from error


def repository_libraries(url: str, revision: str | None, directory: Path) -> tuple[str, tuple[Library, ...]]:
    """リポジトリ url の revision（None は既定のブランチの最新）を directory（まだない一時的な場所）に取り、
    (読んだコミット, ライブラリの一覧) を返す。取り出すのは CppBuild の管理ファイル（.ecobuild/.cppbuild）だけ。"""
    with _clone_config():
        cloned = Git(directory.parent).run("clone", "--quiet", "--no-checkout", "--filter=blob:none", "--",
                                           url, str(directory), check=False)
    if not cloned.ok:
        raise EcoBuildError(ErrorCode.DEPENDENCY_NOT_FOUND, f"{url} を取得できません。", details=cloned.output)
    clone = Git(directory)
    commit = clone.run("rev-parse", "--verify", "--quiet", f"{revision or 'HEAD'}^{{commit}}", check=False)
    if not commit.ok and revision:
        commit = clone.run("rev-parse", "--verify", "--quiet", f"origin/{revision}^{{commit}}", check=False)
    if not commit.ok:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{url} に版 {revision} はありません。",
                            hint="ブランチ・タグ・コミットを指定してください（候補は GitHub のリポジトリで確かめられます）。")
    sha = commit.stdout.strip()
    taken = clone.run("checkout", "--quiet", sha, "--", CONFIG_DIRECTORY, check=False)
    config = directory / CONFIG_DIRECTORY
    if not taken.ok or not config.is_dir():
        raise EcoBuildError(ErrorCode.NOT_LINKABLE,
                            f"{url} は C++（CppBuild）のモジュールではありません（{CONFIG_DIRECTORY} がありません）。",
                            details=taken.output)
    if _migrate.is_old(config):
        raise EcoBuildError(ErrorCode.DEPENDENCY_OLD_FORMAT,
                            f"{url} の版 {sha[:7]} は、CppBuild の管理ファイルが古い形式です。",
                            hint="そのモジュールで ecobuild module upgrade をして取り込んでから、リンクしてください。")
    try:
        return sha, libraries_of(Solution.open(config))
    except Exception as error:
        raise _cppbuild_error(f"{url} を読み込めません。", error) from error


def dependency_links(root: Path) -> dict[str, list[tuple[str, str, str]]]:
    """直接の依存先の名前 → [(このモジュールの Project, 依存先のライブラリの名前, その GUID)]。
    clone のない依存先は、名前が分からないので空（GUID は記録から分かる）。"""
    solution = open_solution(root)
    sources = [s for s in solution.git_sources() if s.recorded_by is None]
    owner, names = {}, {}
    for source in sources:
        if source.present:
            for guid, library in _guid_names(Solution.open(source.config)).items():
                owner[guid], names[guid] = source.name, library
    places = {(Path(s.directory) / s.path).resolve(): s.name for s in sources}
    for guid, reference in solution.settings.get().references.items():   # clone のないもの：記録の置き場所から
        owner.setdefault(guid, places.get((solution.root / reference.solution_directory).resolve()))
    result: dict[str, list[tuple[str, str]]] = {s.name: [] for s in sources}
    for project in solution.subprojects():
        for dependency in project.settings.get().dependencies.values():
            guid = getattr(dependency, "subproject_guid", None)
            if owner.get(guid) in result:
                result[owner[guid]].append((project.name, names.get(guid, ""), guid))
    return {name: sorted(links) for name, links in result.items()}


def link(root: Path, project: str, url: str, *, shared: bool, revision: str | None = None,
         library: str | None = None) -> tuple[str, str]:
    """Projectから、gitのリポジトリにあるモジュールのライブラリ library（None は相手の main）をリンクする
    （revision：ブランチ・タグ・コミット。None は既定のブランチの最新、既にある依存先なら記録の版）。
    (依存先の名前, リンクしたライブラリ) を返す。"""
    solution = open_solution(root)
    _require_project(solution, project)
    before = {s.name for s in solution.git_sources()}
    message = f"{url} をリンクできません。"
    link_type = SubprojectType.SHARED_LIBRARY if shared else SubprojectType.STATIC_LIBRARY
    try:
        # 失敗したら、記録も、今cloneした相手も元に戻る（CppBuildのトランザクション）。_clone_config は外側に：
        # トランザクションの終わりの構成でも、依存先の依存先を clone する。
        with _clone_config(), _transaction(solution, message):
            solution.get_subproject(project).settings.link_git(
                url, revision, solution_path=CONFIG_DIRECTORY, link_type=link_type, subproject=library)
    except EcoBuildError:
        raise
    except AlreadyRegisteredError as error:
        raise EcoBuildError(ErrorCode.ALREADY_EXISTS,
                            f"{project} は {url}{'' if library is None else ' の ' + library} に既にリンクしています。") from error
    except NotRegisteredError as error:
        if error.kind != "subproject" or library is None or error.name != library:
            raise _cppbuild_error(message, error) from error
        raise EcoBuildError(ErrorCode.PROJECT_NOT_FOUND, f"{url} に {library} というProjectはありません。",
                            hint=f"リンクできるライブラリ：{_choices_after_failure(url, revision, solution)}"
                                 "（ecobuild deps libraries <リポジトリ> で一覧）。",
                            details=str(error)) from error
    except GitFetchError as error:
        if not _no_solution(error):
            raise _cppbuild_error(message, error) from error
        others = [f.name for f in error.failures if f.reason.startswith("no CppBuild Solution") and not _same_url(f.url, url)]
        if others:   # リンクしようとしたリポジトリの依存先（の依存先）の記録の版が、古い形式か CppBuild のものでない
            names = "、".join(others)
            raise EcoBuildError(
                ErrorCode.DEPENDENCY_OLD_FORMAT,
                f"{url} は、依存先 {names} の、今の形式の CppBuild の管理ファイルがない版（古い形式か、CppBuild のモジュールでない）を"
                f"記録しているので、リンクできません。",
                hint=f"{names} のモジュールで ecobuild module upgrade、{url} のモジュールで ecobuild deps update {others[0]}"
                     f" をして取り込んでから、もう一度リンクしてください。",
                details=str(error)) from error
        raise EcoBuildError(ErrorCode.NOT_LINKABLE,
                            f"{url} の{'版 ' + revision if revision else '既定のブランチの最新'}に、今の形式の CppBuild の管理ファイル"
                            f"（{CONFIG_DIRECTORY}/solution.json）がありません。C++ のモジュールでないか、古い形式です。",
                            hint="C++ の ECOBuild のモジュールのリポジトリか確かめてください。古い形式なら、そのモジュールで "
                                 "ecobuild module upgrade をして取り込んでから、もう一度リンクしてください。",
                            details=str(error)) from error
    except InvalidValueError as error:
        if error.field == "link_type":
            raise _link_type_error(url, library, shared, revision, error, solution) from error
        if error.field != "revision":
            raise _cppbuild_error(message, error) from error
        # 既に記録している依存先を別のProjectからリンクするときは、記録の版のまま（CppBuild は記録を動かさない）
        name = next((s.name for s in solution.git_sources() if s.recorded_by is None and s.revision in error.allowed), "")
        recorded = error.allowed[0] if error.allowed else ""
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                            f"{url} は依存先 {name} として {recorded[:7]} を記録しています。指定した版 {revision} はそれと違います。",
                            hint=f"版を省けば記録の版でリンクします。記録の版を変えるなら ecobuild deps update {name or '<名前>'} "
                                 f"--at {revision} を使ってください（このモジュールのすべてのリンクが、その版になります）。",
                            details=str(error)) from error
    except NoMainSubprojectError as error:
        raise EcoBuildError(ErrorCode.NOT_LINKABLE, f"{url} のモジュールは、リンクできる形になっていません。",
                            hint="--library を省くと、相手のモジュールの main（最初に作ったProject）にリンクします。main がないか"
                                 "ライブラリでなければ、--library でリンクするライブラリを選んでください"
                                 "（ecobuild deps libraries <リポジトリ> で一覧）。",
                            details=str(error)) from error
    except Exception as error:
        raise _cppbuild_error(message, error) from error
    _write_clone_config(Path(s.directory) for s in solution.git_sources() if s.name not in before)
    sources = solution.git_sources()
    added = [s.name for s in sources if s.name not in before]
    name = added[0] if added else next(s.name for s in sources if s.recorded_by is None and _same_url(s.url, url))
    if library is None:   # 相手の main
        source = next(s for s in sources if s.name == name)
        library = next((l.name for l in _libraries_at(solution, source) if l.main), "")
    return name, library


_KIND_WORDS = {"executable": "実行ファイル", "test": "テスト用", "static_library": "静的ライブラリ",
               "shared_library": "共有ライブラリ", "interface_library": "ヘッダーだけのライブラリ"}


def _link_type_error(url: str, library: str | None, shared: bool, revision: str | None, error, solution) -> EcoBuildError:
    """選んだ Project が、求めた形（静的・共有）でリンクできない（CppBuild の InvalidValueError(field="link_type")）。"""
    allowed = [str(getattr(kind, "value", kind)) for kind in error.allowed or ()]
    words = "・".join(_KIND_WORDS.get(kind, kind) for kind in allowed)
    if not any(kind in {k.value for k in _LINKABLE_TYPES} for kind in allowed):
        return EcoBuildError(ErrorCode.NOT_LINKABLE, f"{library} は{words or 'ライブラリでない Project'}なので、リンクできません。",
                             hint=f"リンクできるのはライブラリだけです（リンクできるライブラリ："
                                  f"{_choices_after_failure(url, revision, solution)}）。",
                             details=str(error))
    switch = ("--shared を外してください" if shared else
              "--shared を付けてください" if SubprojectType.SHARED_LIBRARY.value in allowed else "")
    return EcoBuildError(ErrorCode.NOT_LINKABLE, f"{library} は{'共有' if shared else '静的'}ライブラリとしてはリンクできません。",
                         hint=f"{library} の形式：{words}" + (f"（{switch}）。" if switch else "。"), details=str(error))


def _no_solution(error) -> list[str]:
    """CppBuild の GitFetchError のうち、取った版に Solution（solution.json）がなかった依存先の名前。

    CppBuild はこの理由を型で分けないので、理由の書き出しで見分ける。古い形式の版か、CppBuild のモジュールでない
    リポジトリ（clone は CppBuild が消すので、手元ではどちらか確かめられない）。"""
    return [f.name for f in error.failures if f.reason.startswith("no CppBuild Solution")]


def _same_url(one: str, other: str) -> bool:
    from cppbuild.git_sources import identity
    return identity(one) == identity(other)


def _choices_after_failure(url: str, revision: str | None, solution: Solution | None = None) -> str:
    """リンクに失敗した後の案内に出す、相手のリンクできるライブラリ（読めなければ「分かりません」）。
    既にある依存先（手元に clone がある）なら、その clone（記録の版）から読む。"""
    import tempfile
    try:
        source = next((s for s in solution.git_sources() if s.present and _same_url(s.url, url)), None) if solution else None
        if source is not None and revision is None:
            libraries = libraries_of(Solution.open(source.config))
        else:
            with tempfile.TemporaryDirectory(prefix="ecobuild-", ignore_cleanup_errors=True) as temporary:
                _, libraries = repository_libraries(url, revision, Path(temporary) / "r")
    except Exception:   # 案内のためだけに読むので、読めなくても元の誤りを出す
        return "分かりません"
    return "、".join(l.name + ("（main）" if l.main else "") for l in libraries if l.linkable) or "なし"


def unlink_library(root: Path, name: str, library: str) -> tuple[tuple[str, ...], bool]:
    """依存先 name のライブラリ library へのリンクだけを、すべての Project から外す（記録と clone は残す）。
    それが最後のリンクなら、同じ1つのトランザクションの中で記録も外す（リンクのない記録を残さない。clone は残す）。
    (外した Project, 依存先ごと外したか) を返す。"""
    solution = open_solution(root)
    if not any(s.name == name and s.recorded_by is None for s in solution.git_sources()):
        raise EcoBuildError(ErrorCode.DEPENDENCY_NOT_FOUND, f"依存先 {name} はありません。")
    # 外すものは記録（リンクの GUID）から決める（clone は読まない）。名前が分からなければ（clone なし）、GUID の頭で選べる
    linked = dependency_links(root).get(name, [])
    guids = {guid for _, each, guid in linked
             if each == library or (not each and len(library) >= 8 and guid.lower().startswith(library.lower()))}
    if len(guids) != 1:
        shown = sorted({each or guid[:8] for _, each, guid in linked})
        raise EcoBuildError(ErrorCode.PROJECT_NOT_FOUND, f"依存先 {name} の {library} には、リンクしていません。",
                            hint=f"リンクしているライブラリ：{'、'.join(shown) or 'なし'}（依存先ごと外すなら --library を省きます。"
                                 f"名前の代わりの8文字は、clone がないため名前が分からないライブラリの識別子です）。")
    [target] = guids
    whole = not ({guid for _, _, guid in linked} - {target})
    message = f"依存先 {name} の {library} へのリンクを外せません。"
    removed = []
    try:
        # 依存先ごと外すときは、古い形式の依存先も外せるように形式を確かめない（unlink と同じ）
        with _transaction(solution, message, check_formats=not whole):
            for project in solution.subprojects():
                for key, dependency in list(project.settings.get().dependencies.items()):
                    if getattr(dependency, "subproject_guid", None) == target:
                        project.settings.unlink(key)
                        removed.append(project.name)
            if whole:
                solution.unlink_git_source(name)   # 残りのリンクはないので、記録だけ外れる（clone は残る）
    except EcoBuildError:
        raise
    except Exception as error:
        raise _cppbuild_error(message, error) from error
    return tuple(dict.fromkeys(removed)), whole


def linked_libraries_of(root: Path, name: str) -> tuple[object, list[tuple[str, str, bool, tuple[str, ...]]]]:
    """直接の依存先 name のうち、このモジュールがリンクしているもの（記録から。形式は確かめない）。
    (CppBuild の GitSourceStatus, [(名前, 種類, main か, リンクしている Project)])。名前は clone がなければ識別子の頭8文字と
    「（clone なし）」、種類・main は clone があるときだけ。"""
    solution = open_solution(root)
    source = next((s for s in solution.git_sources() if s.name == name and s.recorded_by is None), None)
    if source is None:
        raise EcoBuildError(ErrorCode.DEPENDENCY_NOT_FOUND, f"依存先 {name} はありません。")
    known = {}
    if source.present:
        try:
            known = {l.guid: l for l in libraries_of(Solution.open(source.config))}
        except Exception:   # 読めなければ名前だけ（種類は補わない）
            known = {}
    users: dict[str, list[str]] = {}
    labels: dict[str, str] = {}
    for project, library, guid in dependency_links(root).get(name, ()):
        users.setdefault(guid, []).append(project)
        labels[guid] = library or f"{guid[:8]}（clone なし）"
    result = []
    for guid, projects in users.items():
        library = known.get(guid)
        result.append((labels[guid], library.kind if library else "", bool(library and library.main), tuple(projects)))
    return source, sorted(result)


def unlink(root: Path, name: str) -> tuple[str, ...]:
    """依存先のリンクを、すべてのProjectから外し、記録を消す。外したProjectを返す。"""
    solution = open_solution(root)
    if not any(s.name == name and s.recorded_by is None for s in solution.git_sources()):
        raise EcoBuildError(ErrorCode.DEPENDENCY_NOT_FOUND, f"依存先 {name} はありません。")
    message = f"依存先 {name} を外せません。"
    try:
        # 古い形式の依存先も、ただ外せるように（形式は確かめない）
        with _transaction(solution, message, check_formats=False):
            report = solution.unlink_git_source(name)   # すべてのProjectからのリンクと、記録（cloneは残る）
    except EcoBuildError:
        raise
    except Exception as error:
        raise _cppbuild_error(message, error) from error
    return tuple(project for project, _ in report.unlinked)


def record_revision(root: Path, name: str, revision: str | None = None) -> str:
    """依存先の記録を、GitHubの既定ブランチの最新（revision：ブランチ・タグ・コミット）にする。記録したコミットを返す。"""
    solution = open_solution(root)
    source = next((s for s in solution.git_sources() if s.name == name and s.recorded_by is None), None)
    if source is None:
        raise EcoBuildError(ErrorCode.DEPENDENCY_NOT_FOUND, f"依存先 {name} はありません。")
    try:
        with _clone_config():
            recorded = solution.set_git_source(source.url, revision).revision
        _write_clone_config(Path(s.directory) for s in solution.git_sources())
        return recorded
    except Exception as error:
        raise _cppbuild_error(f"依存先 {name} の{'最新' if revision is None else ' ' + revision + ' '}を取得できません。",
                              error) from error


def recorders_of(root: Path, url: str) -> tuple[str, ...]:
    """手元に clone のある依存先のうち、url（同じリポジトリ）を自分でも記録しているものの名前。"""
    from cppbuild.git_sources import _records, identity
    solution = open_solution(root)
    try:
        return tuple(sorted(s.name for s in solution.git_sources() if s.present and s.name != _name_of(solution, url)
                            and any(identity(r.url) == identity(url) for r in _records(s.config).values())))
    except Exception as error:
        raise _cppbuild_error("依存先を読み込めません。", error) from error


def _name_of(solution: Solution, url: str) -> str | None:
    from cppbuild.git_sources import identity
    return next((n for n, r in solution.settings.get().git_sources.items() if identity(r.url) == identity(url)), None)


def rename_git_source(root: Path, name: str, url: str) -> tuple[str, Path, Path]:
    """依存先 name の記録を、GitHub で名前が変わった先の url にする（版は同じ）。場所の名前が前の URL から作った既定の
    名前なら、新しい URL の既定の名前にし、その中を指す references も付け替える。clone は動かさない（呼ぶ側が移す）。
    返り値：(新しい場所の名前, 前の clone の場所, 新しい clone の場所)。

    CppBuild に場所の名前を変える API がないので、設定の保存（references は link・unlink だけが変えられる）の中の
    書き出しを直接使う（CppBuild 依頼の下書き：memo の CppBuild依頼 17）。"""
    from copy import deepcopy
    from cppbuild import storage
    from cppbuild.git_sources import base, default_name, identity, unique_name
    from cppbuild.models import GitSource
    from cppbuild.paths import relative
    solution = open_solution(root)
    settings = solution.settings
    try:
        values = deepcopy(settings.get())
        record = values.git_sources.get(name)
        if record is None:
            raise EcoBuildError(ErrorCode.DEPENDENCY_NOT_FOUND, f"依存先 {name} はありません。")
        others = set(values.git_sources) - {name}
        hashed = f"{default_name(record.url)}-{hashlib.sha256(identity(record.url).encode()).hexdigest()[:8]}"
        default = name in (default_name(record.url), hashed)   # 前の URL から作った名前（衝突でハッシュを付けたものも）
        new_name = unique_name(url, others) if default else name
        place = base(solution.root, values)
        before, after = place / name, place / new_name
        del values.git_sources[name]
        values.git_sources[new_name] = GitSource(url, record.revision, record.path)
        if new_name != name:
            for reference in values.references.values():
                found = (solution.root / reference.solution_directory).resolve()
                if found.is_relative_to(before.resolve()):
                    reference.solution_directory = relative(solution.root, after / found.relative_to(before.resolve()))
        settings._validate(values)
        with storage.write_lock(settings.path.parent):
            settings._assert_unchanged()
            settings._publish(values)
    except EcoBuildError:
        raise
    except Exception as error:
        raise _cppbuild_error(f"依存先 {name} の記録を新しい名前にできません。", error) from error
    return new_name, before, after


# 内部 ----------------------------------------------------------------------

def _require_project(solution: Solution, project: str) -> None:
    projects = solution.settings.get().subprojects
    if project not in projects:
        raise EcoBuildError(ErrorCode.PROJECT_NOT_FOUND, f"Project {project} はありません。",
                            hint=f"モジュールのProject：{'、'.join(projects)}")


def _guid_names(solution: Solution) -> dict[str, str]:
    return {solution.get_subproject(name).settings.get().guid: name for name in solution.settings.get().subprojects}


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
    自分のProjectは Subprojects、リンク先は LinkedSubprojects/<Solution名>）。フォルダーなしで作った古いモジュールにも入れる。"""
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


def _target(root: Path, project: str | None, options: BuildOptions, *, run_arguments=None, test_selection=None):
    solution = open_solution(root)
    configuration = options.configuration
    if configuration not in CONFIGURATIONS:
        raise EcoBuildError(ErrorCode.INVALID_CONFIGURATION, f"構成 {configuration} はありません。",
                            hint=f"{'・'.join(CONFIGURATIONS)} のどれかを指定してください。")
    projects = solution.settings.get().subprojects
    if project is not None and project not in projects:
        raise EcoBuildError(ErrorCode.PROJECT_NOT_FOUND, f"Project {project} はありません。",
                            hint=f"モジュールのProject：{'、'.join(projects)}")
    _apply_options(solution, options, run_project=project, run_arguments=run_arguments, test_selection=test_selection)
    check_dependency_formats(solution)
    if options.fetch_git:
        _fetch_missing(solution)
    return solution if project is None else solution.get_subproject(project)


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
                   run_arguments=None, test_selection: dict[str, list[str] | None] | None = None) -> None:
    """ビルド設定をSolutionと各Projectに渡す（CppBuildは保存しないので、開くたびに渡す）。

    test_selection：流すテスト用Projectと、そのケースのパターン（None は全部。_test_selection）。

    構成・生成環境はSolution全体で1つ（依存でつながるProjectは揃っている必要がある）。Projectごとに変えられるのは
    ライブラリの形式・C++の規格・成果物の置き場所・テストの並列数・GoogleTestのZIP。
    """
    overrides = dict(options.projects)
    names = solution.settings.get().subprojects
    unknown = [name for name in overrides if name not in names]
    if unknown:
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"ビルド設定に、ない Project {'、'.join(unknown)} の設定があります。",
                            hint=f"{operation(options.command, 'profile add')} で、その Project の設定を外してください（--clear-project）。")
    for name, own in overrides.items():
        if own.type and LIBRARY_TYPES[own.type] not in solution.get_subproject(name).settings.get().types:
            raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"ビルド設定で、ライブラリでない Project {name} の形式を変えています。",
                                hint="形式（type）を変えられるのはライブラリだけです。")
    try:
        # 構成（Debug／Release）はSolution全体で1つ。Projectは対象を絞るだけで、構成は引き継ぐ。
        # shared：依存先も含め、ライブラリを共有ライブラリにする（Projectの形式の指定が優先）。
        solution.set_build_settings(_solution_settings(
            configuration=options.configuration, parallel=options.parallel, shared_libraries=options.shared,
            architecture=options.architecture, cpp_standard=options.cpp_standard or 20,
            test_continue_on_failure=options.test_continue_on_failure, fetch_git=options.fetch_git,
            test_subprojects=list(test_selection) if test_selection else None,
            tools=ToolSettings(cmake=options.cmake or "cmake", ctest=options.ctest or "ctest"),
            cmake=CMakeSettings(generator=options.generator, toolset=options.toolset, c_compiler=options.c_compiler,
                                cxx_compiler=options.cxx_compiler, toolchain_file=options.toolchain_file,
                                windows_sdk=options.windows_sdk)))
        for name in names:
            own = overrides.get(name, ProjectOptions())
            settings = SubprojectBuildSettings(
                parallel=options.parallel,
                subproject_type=LIBRARY_TYPES[own.type] if own.type else None,
                cpp_standard=own.cpp_standard or INHERIT,
                artifact_directory=own.artifact_directory,
                test_parallel=own.test_parallel or options.test_parallel,
                googletest_archive=own.googletest_archive or options.googletest_archive)
            if name == run_project and run_arguments is not None:
                settings.run_arguments = list(run_arguments)
            if test_selection and test_selection.get(name) is not None:
                settings.test_cases = list(test_selection[name])
            solution.get_subproject(name).set_build_settings(settings)
    except Exception as error:
        raise _cppbuild_error("ビルド設定を渡せません。", error) from error


def _tests(solution: Solution) -> list[str]:
    return [name for name in solution.settings.get().subprojects
            if SubprojectType.TEST in solution.get_subproject(name).settings.get().types]


def linked_libraries(root: Path, project: str) -> list[str]:
    """Projectがリンクしている、同じモジュールのライブラリ。"""
    solution = open_solution(root)
    _require_project(solution, project)
    by_guid = _guid_names(solution)
    names = [by_guid[d.subproject_guid] for d in solution.get_subproject(project).settings.get().dependencies.values()
             if getattr(d, "subproject_guid", None) in by_guid]
    return [n for n in names if SubprojectType.STATIC_LIBRARY in solution.get_subproject(n).settings.get().types]


def is_test_project(root: Path, project: str) -> bool:
    solution = open_solution(root)
    return project in _tests(solution)


def _executables(solution: Solution) -> list[str]:
    return [name for name in solution.settings.get().subprojects
            if SubprojectType.EXECUTABLE in solution.get_subproject(name).settings.get().types]


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
    if isinstance(error, GitFetchError):
        old = _no_solution(error)
        if old:
            return EcoBuildError(
                ErrorCode.DEPENDENCY_OLD_FORMAT,
                f"{message}（依存先 {'、'.join(old)} の記録の版に、今の形式の CppBuild の管理ファイルがありません。"
                f"古い形式か、CppBuild のモジュールではありません）",
                hint=f"古い形式の版を記録しているなら、その依存先のモジュールで ecobuild module upgrade をして取り込んでから、"
                     f"このモジュールで ecobuild deps update {old[0] if len(old) == 1 else '<名前>'} を実行してください"
                     f"（依存先の依存先なら、それを記録している直接の依存先を新しくします）。C++ のモジュールでなければ、"
                     f"ecobuild deps remove で外してください。",
                details=details)
    if isinstance(error, AlreadyRegisteredError):
        return EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{message}（{error.name} は既にあります）", details=details)
    if isinstance(error, NotRegisteredError):
        code = {"subproject": ErrorCode.PROJECT_NOT_FOUND, "git_source": ErrorCode.DEPENDENCY_NOT_FOUND,
                "dependency": ErrorCode.DEPENDENCY_NOT_FOUND}.get(error.kind)
        if code is not None:
            return EcoBuildError(code, f"{message}（{error.name} はありません）", details=details)
    if isinstance(error, InvalidValueError):
        hint = f"{error.field} に指定できるのは {'・'.join(map(str, error.allowed))} です。" if error.allowed else None
        return EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{message}（{error.field} の値 {error.value!r} は使えません）",
                             hint=hint, details=details)
    return EcoBuildError(ErrorCode.CPPBUILD_ERROR, message, details=details)


@contextmanager
def _transaction(solution: Solution, message: str, *, check_formats: bool = True):
    """設定の変更と、それを反映する更新（生成ファイルの作り直しとCMakeの構成）を一体にする。

    中で例外が起きるか、更新に失敗したら、書いた管理ファイル・生成ファイルと、今cloneした依存先を元に戻す
    （CppBuildの Solution.transaction）。ソースファイルとビルドツリーは戻さない。更新の失敗は EcoBuildError にする。
    check_formats：先に依存先の形式を確かめる（古い依存先を外すときは確かめない）。
    """
    if check_formats:
        check_dependency_formats(solution)
    with solution.transaction() as report:
        yield report
    if not report.success:
        update = report.update
        processes = update.processes if hasattr(update, "processes") else (update.process,)
        raise EcoBuildError(ErrorCode.CPPBUILD_ERROR, f"{message}CMakeの構成に失敗したので、設定を元に戻しました。",
                            hint="パス・ターゲット名等を確かめてください（詳細はCMakeの出力）。",
                            details=_joined(tuple(_process(p) for p in processes)))
