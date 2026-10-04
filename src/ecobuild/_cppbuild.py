"""CppBuild の呼び出し（非公開）。"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from cppbuild import ProjectBuildSettings, ProjectType, Solution, SolutionBuildSettings

from .config import DEPENDENCY_DIRECTORY, ProjectNames
from .errors import EcoBuildError, ErrorCode

CONFIG_DIRECTORY = ".cppbuild"
GENERATED_FILE_NAMES = ("CMakeLists.txt", "CppBuildTopLevel.cmake")

# CppBuildのファイルテンプレートとして登録する既定の素材（名前 → 素材ファイル）
TEMPLATES = {
    "header": "header.h",
    "source": "source.cpp",
    "pch": "pch.h",
    "test": "test.cpp",
    "main": "main.cpp",
}


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
        return Solution.open(root / CONFIG_DIRECTORY)
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
        library.add_file(f"include/{header}", template_name="header", auto_update=False)
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


def build(root: Path, *, project: str | None, configuration: str) -> BuildOutcome:
    target = _target(root, project, configuration)
    try:
        report = target.build()
    except Exception as error:
        raise _cppbuild_error("ビルドを実行できません。", error) from error
    outcome = BuildOutcome(report.success, tuple(_process(p) for p in report.processes), tuple(report.artifacts))
    if not outcome.success:
        raise EcoBuildError(ErrorCode.BUILD_FAILED, "ビルドに失敗しました。", details=_joined(outcome.processes))
    return outcome


def test(root: Path, *, project: str | None, configuration: str) -> TestOutcome:
    target = _target(root, project, configuration)
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


def run(root: Path, *, project: str | None, configuration: str, arguments: str) -> BuildOutcome:
    solution = open_solution(root)
    name = project or _single_executable(solution)
    target = _target(root, name, configuration, run_arguments=shlex.split(arguments))
    try:
        report = target.run()
        report = report.wait() if hasattr(report, "wait") else report
    except Exception as error:
        raise _cppbuild_error("実行できません。", error) from error
    outcome = BuildOutcome(report.success, tuple(_process(p) for p in report.processes))
    if not outcome.success:
        raise EcoBuildError(ErrorCode.RUN_FAILED, "実行に失敗しました。", details=_joined(outcome.processes))
    return outcome


def project_at(root: Path, path: Path) -> str | None:
    """pathが属するProjectの名前。どのProjectにも属さなければNone。"""
    solution = open_solution(root)
    path = path.resolve()
    for name in solution.settings.get().projects:
        directory = Path(solution.get_project(name).root).resolve()
        if path == directory or directory in path.parents:
            return name
    return None


def is_generated_or_managed(relative_path: str) -> bool:
    """CppBuildの生成ファイル・管理ファイル（コミット対象）か。"""
    parts = Path(relative_path).parts
    if not parts or parts[0] == DEPENDENCY_DIRECTORY:
        return False
    if parts[-1] in GENERATED_FILE_NAMES:
        return True
    return CONFIG_DIRECTORY in parts and "output" not in parts


# 内部 ----------------------------------------------------------------------

def _register_templates(solution: Solution) -> None:
    materials = resources.files("ecobuild") / "templates"
    for name, file_name in TEMPLATES.items():
        # CppBuildは素材をSolutionの中から読み込むので、いったんSolutionの中へ置く。
        staging = solution.root / f".ecobuild-template-{file_name}"
        staging.write_bytes((materials / file_name).read_bytes())
        try:
            solution.create_file_template(name, staging.name)
        finally:
            staging.unlink()


def _target(root: Path, project: str | None, configuration: str, *, run_arguments=None):
    solution = open_solution(root)
    try:
        if project is None:
            solution.set_build_settings(SolutionBuildSettings(configuration=configuration))
            return solution
        target = solution.get_project(project)
        settings = ProjectBuildSettings(configuration=configuration)
        if run_arguments is not None:
            settings.run_arguments = list(run_arguments)
        target.set_build_settings(settings)
        return target
    except Exception as error:
        raise _cppbuild_error(f"Project {project!r} を準備できません。", error) from error


def _single_executable(solution: Solution) -> str:
    executables = [name for name in solution.settings.get().projects
                   if ProjectType.EXECUTABLE in solution.get_project(name).settings.get().types]
    if len(executables) != 1:
        raise EcoBuildError(
            ErrorCode.RUN_FAILED,
            "実行するProjectを決められません。" if executables else "実行ファイルのProjectがありません。",
            hint="--project で実行するProjectを指定してください。" if executables else None,
            details=executables,
        )
    return executables[0]


def _process(report) -> ProcessOutput:
    return ProcessOutput(" ".join(report.command), report.returncode, report.output)


def _joined(processes) -> str:
    return "\n".join(p.output for p in processes if p.output)


def _cppbuild_error(message: str, error: Exception) -> EcoBuildError:
    return EcoBuildError(ErrorCode.CPPBUILD_ERROR, message, details=f"{type(error).__name__}: {error}")
