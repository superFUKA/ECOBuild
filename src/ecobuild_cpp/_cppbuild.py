"""CppBuild の呼び出し（cpp 型の内部）。"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from cppbuild import ProjectBuildSettings, ProjectType, Solution, SolutionBuildSettings

from ecobuild.config import ProjectNames
from ecobuild.errors import EcoBuildError, ErrorCode

CONFIG_DIRECTORY = ".cppbuild"
DEPENDENCY_DIRECTORY = "deps"   # 依存先のcloneの置き場所（.gitignore で除外）
CONFIGURATIONS = ("Debug", "Release", "RelWithDebInfo", "MinSizeRel")   # CMakeの標準の構成
# CMakeのビルドツリー（中間ファイル）の置き場所。CppBuildの既定（.cppbuild/output/intermediate）より
# 約25文字短い、モジュール直下の build/ にする（Windowsの260文字の制限への対策）。
# CppBuildの設定は.cppbuildからの相対で、保存されないため、Solutionを開くたびに設定する。
BUILD_DIRECTORY = "build"
GENERATED_FILE_NAMES = ("CMakeLists.txt", "CppBuildTopLevel.cmake")

# CppBuildのファイルテンプレートとして登録する既定の素材（名前 → 素材ファイル）
TEMPLATES = {
    "header": "header.h",
    "library": "library.h",
    "source": "source.cpp",
    "pch": "pch.h",
    "test": "test.cpp",
    "main": "main.cpp",
    "bench": "bench.cpp",
    "unit_test": "unit_test.cpp",
}

# project add の種類 → CppBuildの種類
PROJECT_KINDS = {
    "library": ProjectType.STATIC_LIBRARY,
    "app": ProjectType.EXECUTABLE,
    "test": ProjectType.TEST,
    "bench": ProjectType.EXECUTABLE,
}
HEADER_SUFFIXES = (".h", ".hpp", ".hh", ".hxx")
SOURCE_SUFFIXES = (".cpp", ".cc", ".cxx")


@dataclass(frozen=True)
class BuildOptions:
    """1回のビルド等の設定（名前付きビルド設定から作る）。"""
    configuration: str = "Debug"
    parallel: int = 1
    shared: bool = False      # ライブラリ（依存先を含む）を共有ライブラリにする


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


def create_module_solution(root: Path, name: str, projects: ProjectNames) -> Solution:
    """Solutionと、ライブラリ・テスト用・実行ファイル用のProjectを作る（生成はしない）。"""
    try:
        solution = Solution.create(root, name)
        data = solution.settings.get()
        data.dependency_directories = [DEPENDENCY_DIRECTORY]
        solution.settings.save(data)
        _register_templates(solution)
        # ライブラリを最初に作り、相手からのリンク先（main_project）にする。
        library = solution.add_project(projects.library, projects.library, ProjectType.STATIC_LIBRARY)
        header = f"{projects.library}/{projects.library}.h"
        _add_library_header(library, f"include/{header}")
        library.add_file(f"src/{projects.library}.cpp", template_name="source",
                         replacements={"header": header}, auto_update=False)
        test = solution.add_project(projects.test, projects.test, ProjectType.TEST)
        test.settings.link_project(library, ProjectType.STATIC_LIBRARY)
        test.add_file(f"src/{projects.test}.cpp", template_name="test",
                      replacements={"header": header, "suite": projects.library}, auto_update=False)
        if projects.app is not None:
            app = solution.add_project(projects.app, projects.app, ProjectType.EXECUTABLE)
            app.settings.link_project(library, ProjectType.STATIC_LIBRARY)
            app.add_file("src/main.cpp", template_name="main", replacements={"header": header}, auto_update=False)
        return solution
    except EcoBuildError:
        raise
    except Exception as error:
        raise _cppbuild_error("CppBuildでSolutionを作成できません。", error) from error


def update(root: Path) -> BuildOutcome:
    """構成と生成ファイル（CMakeLists.txt等）を最新にする。"""
    solution = open_solution(root)
    try:
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
    """CppBuildの生成ファイル（管理ファイルから作り直せるもの）か。"""
    parts = Path(relative_path).parts
    return bool(parts) and parts[0] != DEPENDENCY_DIRECTORY and parts[-1] in GENERATED_FILE_NAMES


def is_generated_or_managed(relative_path: str) -> bool:
    """CppBuildの生成ファイル・管理ファイル（コミット対象）か。"""
    parts = Path(relative_path).parts
    if not parts or parts[0] == DEPENDENCY_DIRECTORY:
        return False
    if parts[-1] in GENERATED_FILE_NAMES:
        return True
    return CONFIG_DIRECTORY in parts and "output" not in parts


# Project ---------------------------------------------------------------------

@dataclass(frozen=True)
class ProjectSummary:
    name: str
    kind: str                 # static_library / executable / test 等（CppBuildの種類）
    directory: str            # モジュールからの相対
    links: tuple[str, ...]    # リンクしているProject（同じSolution）と依存先のモジュール


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
        result.append(ProjectSummary(name, data.initial_type.value, directory, links))
    return tuple(result)


def add_project(root: Path, name: str, kind: str, *, library: str, library_header: str) -> tuple[str, ...]:
    """Projectを作り、ライブラリ以外はモジュールのライブラリをリンクする。作ったファイルを返す。"""
    if kind not in PROJECT_KINDS:
        raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"種類 {kind} はありません。",
                            hint=f"{'・'.join(PROJECT_KINDS)} のどれかを指定してください。")
    solution = open_solution(root)
    if name in solution.settings.get().projects:
        raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"Project {name} は既にあります。")
    if (root / name).exists():
        raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{root / name} は既に存在します。")
    try:
        _ensure_templates(solution)
        project = solution.add_project(name, name, PROJECT_KINDS[kind])
        files = []
        if kind == "library":
            header = f"{name}/{name}.h"
            files += [f"include/{header}", f"src/{name}.cpp"]
            _add_library_header(project, files[0])
            project.add_file(files[1], template_name="source", replacements={"header": header}, auto_update=False)
        else:
            project.settings.link_project(solution.get_project(library), ProjectType.STATIC_LIBRARY)
            template, file_name = {"app": ("main", "main.cpp"), "test": ("test", f"{name}.cpp"),
                                   "bench": ("bench", "bench.cpp")}[kind]
            files.append(f"src/{file_name}")
            replacements = {"header": library_header}
            if kind == "test":
                replacements["suite"] = name
            project.add_file(files[0], template_name=template, replacements=replacements, auto_update=False)
        solution.update()
        return tuple(f"{name}/{f}" for f in files)
    except EcoBuildError:
        raise
    except Exception as error:
        raise _cppbuild_error(f"Project {name} を作れません。", error) from error


def remove_project(root: Path, name: str) -> None:
    """Projectを、他のProjectからのリンクごと外す（ファイルは呼び出し側が消す）。"""
    solution = open_solution(root)
    _require_project(solution, name)
    try:
        guid = solution.get_project(name).settings.get().guid
        for other in solution.projects():
            if other.name == name:
                continue
            for key, dependency in list(other.settings.get().dependencies.items()):
                if getattr(dependency, "project_guid", None) == guid:
                    other.settings.unlink(key)
        solution.remove_project(name)
        solution.update()
    except Exception as error:
        raise _cppbuild_error(f"Project {name} を外せません。", error) from error


def set_pch(root: Path, project: str, *, enable: bool) -> str | None:
    """PCHを有効にする（include/<Project>/pch.h をテンプレートから作る）か、外す。PCHのパスを返す。"""
    solution = open_solution(root)
    _require_project(solution, project)
    target = solution.get_project(project)
    try:
        if not enable:
            target.settings.clear_pch()
            solution.update()
            return None
        _ensure_templates(solution)
        header = f"include/{project}/pch.h"
        if not (target.root / header).exists():
            target.add_file(header, template_name="pch", auto_update=False)
        target.settings.set_pch(project_headers=[header])
        solution.update()
        return f"{project}/{header}"
    except Exception as error:
        raise _cppbuild_error(f"Project {project} のPCHを設定できません。", error) from error


# ファイル ---------------------------------------------------------------------

def project_root(root: Path, project: str) -> Path:
    solution = open_solution(root)
    _require_project(solution, project)
    return Path(solution.get_project(project).root)


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


def link(root: Path, project: str, url: str, *, shared: bool) -> str:
    """Projectから、gitのリポジトリにあるモジュールのライブラリをリンクする。依存先の名前を返す。"""
    solution = open_solution(root)
    _require_project(solution, project)
    before = {s.name for s in solution.git_sources()}
    try:
        solution.get_project(project).settings.link_git(
            url, link_type=ProjectType.SHARED_LIBRARY if shared else ProjectType.STATIC_LIBRARY)
        solution.update()
    except Exception as error:
        text = str(error)
        if "already registered" in text:
            raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{url} は既にリンクしています。") from error
        raise _cppbuild_error(f"{url} をリンクできません。", error) from error
    added = [s.name for s in solution.git_sources() if s.name not in before]
    return added[0] if added else next(s.name for s in solution.git_sources() if s.url == url)


def unlink(root: Path, name: str) -> tuple[str, ...]:
    """依存先のリンクを、すべてのProjectから外し、記録を消す。外したProjectを返す。"""
    solution = open_solution(root)
    source = next((s for s in solution.git_sources() if s.name == name and s.recorded_by is None), None)
    if source is None:
        raise EcoBuildError(ErrorCode.DEPENDENCY_NOT_FOUND, f"依存先 {name} はありません。")
    try:
        guids = set(_guid_names(Solution.open(source.config)).keys()) if source.present else set()
        unlinked = []
        for project in solution.projects():
            for key, dependency in list(project.settings.get().dependencies.items()):
                if getattr(dependency, "project_guid", None) in guids:
                    project.settings.unlink(key)
                    unlinked.append(project.name)
        solution.remove_git_source(name)
        solution.update()
    except EcoBuildError:
        raise
    except Exception as error:
        raise _cppbuild_error(f"依存先 {name} を外せません。", error) from error
    return tuple(unlinked)


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


def _shared_capable(solution: Solution) -> list[str]:
    """共有ライブラリにできるライブラリ（依存先を含む）のGUID。"""
    solutions = [solution]
    for source in solution.git_sources():
        if source.present:
            solutions.append(Solution.open(source.config))
    return [s.get_project(name).settings.get().guid for s in solutions for name in s.settings.get().projects
            if ProjectType.SHARED_LIBRARY in s.get_project(name).settings.get().types]


def _add_library_header(project, path: str) -> None:
    """ライブラリの見出しのヘッダー。書き出しのマクロ（<名前>_API）を定義する。

    Windowsで共有ライブラリ（DLL）にすると、マクロを付けたものだけが書き出される。マクロの切り替えに使う定義は
    共有ライブラリのときだけ付ける：ライブラリ自身には <名前>_EXPORTS、使う側には <名前>_SHARED。
    """
    prefix = re.sub(r"[^A-Za-z0-9]", "_", project.name).upper()
    names = {"api": f"{prefix}_API", "exports": f"{prefix}_EXPORTS", "shared": f"{prefix}_SHARED"}
    project.add_file(path, template_name="library", replacements=names, auto_update=False)
    data = project.settings.get()
    shared = data.types[ProjectType.SHARED_LIBRARY]
    shared.compile_definitions.append(names["exports"])
    shared.public_definitions.append(names["shared"])
    project.settings.save(data)


def _ensure_templates(solution: Solution) -> None:
    """後から増えたテンプレート（bench等）を、古いモジュールにも登録する。"""
    existing = set(solution.settings.get().file_templates)
    missing = {name: file_name for name, file_name in TEMPLATES.items() if name not in existing}
    if missing:
        _register_templates(solution, missing)

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
    return SolutionBuildSettings(intermediate_directory=f"../{BUILD_DIRECTORY}", **values)


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
    try:
        # 構成（Debug／Release）はSolution全体で1つ。Projectは対象を絞るだけで、構成は引き継ぐ。
        types = {guid: ProjectType.SHARED_LIBRARY for guid in _shared_capable(solution)} if options.shared else {}
        solution.set_build_settings(_solution_settings(configuration=configuration, parallel=options.parallel,
                                                       project_types=types))
        if project is None:
            return solution
        target = solution.get_project(project)
        settings = ProjectBuildSettings()
        if run_arguments is not None:
            settings.run_arguments = list(run_arguments)
        target.set_build_settings(settings)
        return target
    except Exception as error:
        raise _cppbuild_error(f"Project {project!r} を準備できません。", error) from error


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
    return EcoBuildError(ErrorCode.CPPBUILD_ERROR, message, details=f"{type(error).__name__}: {error}")
