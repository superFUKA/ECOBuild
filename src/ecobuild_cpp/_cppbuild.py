"""CppBuild の呼び出し（cpp 型の内部）。"""

from __future__ import annotations

import shlex
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from cppbuild import (ARCHITECTURES, CONFIGURATIONS, CPP_STANDARDS, GENERATORS, INHERIT, AlreadyRegisteredError,
                      CMakeSettings, InvalidValueError, NoMainProjectError, NotRegisteredError, ProjectBuildSettings,
                      ProjectType, Solution, SolutionBuildSettings, SolutionFolderSettings, ToolSettings)

from ecobuild.config import DIRECTORY
from ecobuild.errors import EcoBuildError, ErrorCode
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

# module new の --kind：最初に作るProject（app：実行ファイル、library：ライブラリとテスト用、none：作らない）
NEW_KINDS = ("app", "library", "none")

# project add の種類 → CppBuildの種類
PROJECT_KINDS = {
    "library": ProjectType.STATIC_LIBRARY,
    "app": ProjectType.EXECUTABLE,
    "test": ProjectType.TEST,
    "bench": ProjectType.EXECUTABLE,
}
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


def create_module_solution(root: Path, name: str, kind: str, project: str | None = None) -> Solution:
    """Solutionと、最初のProjectを作る（生成はしない）。kind：app＝実行ファイル <Project名>、
    library＝ライブラリ <Project名> とテスト用 <Project名>Test、none＝Projectを作らない。
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
        elif kind == "library":
            _create_library(solution, project or name, test=True)
        return solution
    except EcoBuildError:
        raise
    except Exception as error:
        raise _cppbuild_error("CppBuildでSolutionを作成できません。", error) from error


def _create_library(solution: Solution, name: str, *, test: bool) -> list[str]:
    """ライブラリ（ヘッダー include/<名前>/<名前>.h と src/<名前>.cpp）と、test ならテスト用 <名前>Test。"""
    project = solution.add_project(name, name, ProjectType.STATIC_LIBRARY)
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
    project.settings.link_project(solution.get_project(library), ProjectType.STATIC_LIBRARY)
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


def test_project_of(library: str) -> str:
    """ライブラリと組のテスト用Project（ライブラリを作るときに一緒に作る。file add のテストの置き場所）。"""
    return f"{library}Test"


def update(root: Path, options: BuildOptions | None = None) -> BuildOutcome:
    """構成と生成ファイル（CMakeLists.txt等）を最新にする。options：構成に使うビルド設定（生成器等。既定はCppBuildの既定）。"""
    solution = open_solution(root)
    if options is not None:
        _apply_options(solution, options)
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
        report = solution.fetch_git_sources()
    except Exception as error:
        raise _cppbuild_error("依存先を取得できません。", error) from error
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

    library：ライブラリと、test ならテスト用 <名前>Test（I-022）。app・test・bench：link のライブラリ
    （省略時は、ライブラリが1つならそれ）をリンクする。test・bench にはライブラリが要る。app はなくてもよい。
    """
    if kind not in PROJECT_KINDS:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"種類 {kind} はありません。",
                            hint=f"{'・'.join(PROJECT_KINDS)} のどれかを指定してください。")
    solution = open_solution(root)
    existing = solution.settings.get().projects
    for each in [name] + ([test_project_of(name)] if kind == "library" and test else []):
        if each in existing:
            raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"Project {each} は既にあります。")
        if (root / each).exists():
            raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{root / each} は既に存在します。")
    library = None
    if kind == "library":
        if link:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "--link は library では使えません。")
    else:
        library = _library_to_link(solution, link)
        if library is None and kind != "app":
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                                f"{'テスト' if kind == 'test' else '性能測定'}のProjectには、リンクするライブラリが要ります。",
                                hint="先に project add <名前> --kind library でライブラリを作ってください。")
    try:
        _ensure_templates(solution)
        files = (_create_library(solution, name, test=test) if kind == "library"
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
        # 失敗したら、記録も、今cloneした相手も元に戻る（CppBuildのトランザクション）。
        with _transaction(solution, message):
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
        return solution.set_git_source(source.url).revision
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
    return solution if project is None else solution.get_project(project)


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
                            hint="ecobuild profile add で、その Project の設定を外してください（--clear-project）。")
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
