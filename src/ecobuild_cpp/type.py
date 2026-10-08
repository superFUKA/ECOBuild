"""型 cpp：Project・ファイル・ビルド・テスト・依存先を、CppBuildで扱う。"""

from __future__ import annotations

import hashlib
import os
from importlib import metadata
from pathlib import Path

from ecowork import workspace as ws
from ecowork.git import Git

from ecobuild import ci_workflow
from ecobuild.config import ModuleConfig, Profile, ProjectNames
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild.fsutil import remove_tree
from ecobuild.module_type import ModuleType
from ecobuild.results import (BuildResult, DependencyChange, DependencyState, FilesChanged, LinkResult,
                              PrepareResult, ProjectSummary, RunResult, TestCaseResult, TestResult)

from . import _cppbuild

COMMAND = "ecobuild"

# CppBuildは生成・管理ファイルをLFで書く。gitの改行変換（Windowsのcore.autocrlf=true等）で
# CRLFにされると、生成し直すたびに「変更あり」になるため、LFに固定する。
GITATTRIBUTES = """\
# ECOBuild：CppBuildの生成ファイル・管理ファイルの改行をLFに固定する
CMakeLists.txt text eol=lf
*.cmake text eol=lf
.cppbuild/** text eol=lf
ecobuild.toml text eol=lf
"""

GITIGNORE = """\
# 依存先のclone・ビルドの中間ファイル
/deps/
/build/

# CppBuildの中間ファイル・成果物
.cppbuild/output/
"""


def _cppbuild_version() -> str:
    try:
        distribution = metadata.distribution("cppbuild")
        return distribution.read_text("direct_url.json") or distribution.version
    except metadata.PackageNotFoundError:
        return ""


def _fingerprint(root: Path) -> str:
    """CppBuildの update の結果を左右するものの要約。"""
    digest = hashlib.sha256(_cppbuild_version().encode("utf-8"))
    for directory, children, files in os.walk(root):
        relative = Path(directory).relative_to(root)
        parts = relative.parts
        # .git、ビルドの中間ファイル（build/、依存先の build/）、CppBuildの出力（.cppbuild/output）は見ない
        children[:] = sorted(c for c in children
                             if c != ".git"
                             and not (c == _cppbuild.BUILD_DIRECTORY
                                      and (parts == () or (len(parts) == 2 and parts[0] == _cppbuild.DEPENDENCY_DIRECTORY)))
                             and not (c == "output" and parts[-1:] == (_cppbuild.CONFIG_DIRECTORY,)))
        for name in sorted(files):
            path = relative / name
            digest.update(path.as_posix().encode("utf-8") + b"\0")
            if _cppbuild.CONFIG_DIRECTORY in parts or name in _cppbuild.GENERATED_FILE_NAMES:
                digest.update((root / path).read_bytes())
    return digest.hexdigest()


class CppType(ModuleType):
    name = "cpp"
    description = "C++。CppBuildでProject・ファイル・ビルド・テスト・依存先を管理する"
    generated_note = f"CppBuildの生成ファイル（{'・'.join(_cppbuild.GENERATED_FILE_NAMES)}）"

    # モジュールの作成 -------------------------------------------------------------

    @classmethod
    def new_config(cls, name: str, *, app: bool) -> ModuleConfig:
        return ModuleConfig(name=name, type=cls.name,
                            projects=ProjectNames(name, name + "Test", name + "App" if app else None))

    @classmethod
    def populate(cls, root: Path, config: ModuleConfig) -> None:
        _cppbuild.create_module_solution(root, config.name, config.projects)
        _cppbuild.update(root)

    @classmethod
    def gitignore(cls) -> str:
        return GITIGNORE

    @classmethod
    def gitattributes(cls) -> str:
        return GITATTRIBUTES

    @classmethod
    def readme_usage(cls, config: ModuleConfig) -> str:
        return """## ECOBuildなしで使う

CMake 3.24以上とC++20のコンパイラがあれば、cloneしたままビルドできます（依存先は構成時に取得されます）。

```sh
cmake -S . -B build
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
# 変えるときは ecobuild ci init の --os・--configuration・--shared・--branches（設定は ecobuild.toml の [ci]）。
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
        run: cmake -S . -B build -DCMAKE_BUILD_TYPE=${{{{ matrix.configuration }}}} -DBUILD_SHARED_LIBS=${{{{ matrix.shared }}}}
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
    def doctor_items(cls):
        from ecobuild.tooling import CheckItem
        try:
            from cppbuild import Environment, EnvironmentOptions
            report = Environment.check(EnvironmentOptions(require_ctest=True))
        except Exception as error:  # CppBuildの診断そのものが失敗した
            return [CheckItem("CMake・コンパイラ", False, True, f"{type(error).__name__}: {error}",
                              "CMake と C++ コンパイラをインストールしてください。", "install")]
        result = []
        for item in report.items:
            detail = " ".join(part for part in (item.version or "", item.path or "") if part) or item.detail
            result.append(CheckItem(item.name, item.success, True, detail if item.success else (item.detail or detail),
                                    item.action or "CMake と C++ コンパイラ（Windows：Visual Studio のC++、"
                                                   "Linux：g++）が必要です。", "install"))
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

    def build_options(self, profile: Profile | None, configuration: str) -> _cppbuild.BuildOptions:
        selected = profile or Profile()
        return _cppbuild.BuildOptions(configuration or selected.configuration, selected.parallel, selected.shared)

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

    @property
    def library_header(self) -> str:
        library = self.module.config.projects.library
        return f"{library}/{library}.h"

    def project_at(self, path: Path) -> str | None:
        return _cppbuild.project_at(self.root, Path(path))

    def executable_at(self, path: Path) -> str | None:
        project = self.project_at(path)
        executables = {p.name for p in self.projects() if p.kind == "executable"}
        return project if project in executables else None

    def projects(self) -> tuple[ProjectSummary, ...]:
        return _cppbuild.list_projects(self.root)

    def add_project(self, name: str, kind: str) -> FilesChanged:
        files = _cppbuild.add_project(self.root, name, kind, library=self.module.config.projects.library,
                                      library_header=self.library_header)
        return FilesChanged("project add", files, name)

    def remove_project(self, name: str) -> FilesChanged:
        projects = self.module.config.projects
        if name in (projects.library, projects.test, projects.app):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                                f"Project {name} は ecobuild.toml の [projects] にある基本のProjectです。",
                                hint="基本のProject（ライブラリ・テスト・実行ファイル）は外せません。")
        directory = _cppbuild.project_root(self.root, name)
        _cppbuild.remove_project(self.root, name)
        if directory.is_dir():
            remove_tree(directory)
        return FilesChanged("project remove", (directory.relative_to(self.root).as_posix(),), name)

    def set_pch(self, project: str, *, enable: bool) -> FilesChanged:
        header = _cppbuild.set_pch(self.root, project, enable=enable)
        return FilesChanged("pch" if enable else "pch off", (header,) if header else (), project)

    # ファイル -------------------------------------------------------------------------

    def add_file(self, path: Path, *, test: bool) -> FilesChanged:
        """ライブラリの src/ のソースなら、テスト用Projectの同じ構成の場所にテストも足す（I-014）。"""
        project, relative = self._in_project(path)
        header = self._header_for(project, relative)
        added = [_cppbuild.add_file(self.root, project, relative, replacements={"header": header})]
        mirror = self._test_mirror(project, relative)
        if test and mirror is not None:
            added.append(_cppbuild.add_file(self.root, self.module.config.projects.test, mirror,
                                            template="unit_test",
                                            replacements={"header": header, "suite": Path(relative).stem}))
        return FilesChanged("file add", tuple(added), project)

    def remove_file(self, path: Path, *, test: bool) -> FilesChanged:
        project, relative = self._in_project(path)
        removed = [_cppbuild.remove_file(self.root, project, relative)]
        mirror = self._test_mirror(project, relative)
        test_project = self.module.config.projects.test
        if test and mirror is not None and (_cppbuild.project_root(self.root, test_project) / mirror).is_file():
            removed.append(_cppbuild.remove_file(self.root, test_project, mirror))
        return FilesChanged("file remove", tuple(removed), project)

    def move_file(self, source: Path, destination: Path, *, test: bool) -> FilesChanged:
        project, relative = self._in_project(source)
        other, target = self._in_project(destination)
        if other != project:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "別のProjectへは移動できません。",
                                hint="移動先も同じProjectのディレクトリの中にしてください。")
        moved = list(_cppbuild.move_file(self.root, project, relative, target))
        mirror, mirror_target = self._test_mirror(project, relative), self._test_mirror(project, target)
        test_project = self.module.config.projects.test
        if test and mirror and mirror_target and (_cppbuild.project_root(self.root, test_project) / mirror).is_file():
            moved += _cppbuild.move_file(self.root, test_project, mirror, mirror_target)
        return FilesChanged("file move", tuple(moved), project)

    def _in_project(self, path: Path) -> tuple[str, str]:
        """パス（今いるディレクトリからの相対か絶対）から、Projectとその中の相対パスを決める（I-027）。"""
        absolute = (Path.cwd() / Path(path)).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        project = _cppbuild.project_at(self.root, absolute)
        if project is None:
            raise EcoBuildError(ErrorCode.NOT_IN_PROJECT, f"{path} はどのProjectの中でもありません。",
                                hint="Projectのディレクトリの中のパスを指定してください（ecobuild project list で一覧）。")
        relative = absolute.relative_to(_cppbuild.project_root(self.root, project).resolve()).as_posix()
        return project, relative

    def _header_for(self, project: str, relative: str) -> str:
        """ソースが読み込むヘッダー：include/ の同じ構成の場所にあればそれ、なければライブラリのヘッダー。"""
        path = Path(relative)
        if path.parts[:1] == ("src",):
            candidate = Path("include", project, *path.parts[1:]).with_suffix(".h")
            if (_cppbuild.project_root(self.root, project) / candidate).is_file():
                return Path(project, *path.parts[1:]).with_suffix(".h").as_posix()
        return self.library_header

    def _test_mirror(self, project: str, relative: str) -> str | None:
        """ライブラリの src/ のソースに対応する、テスト用Projectのテストファイル（src/... /<名前>Test.cpp）。"""
        path = Path(relative)
        if project != self.module.config.projects.library or path.parts[:1] != ("src",) \
                or path.suffix.lower() not in _cppbuild.SOURCE_SUFFIXES:
            return None
        return path.with_name(f"{path.stem}Test{path.suffix}").as_posix()

    # 生成ファイルの更新（変わっていなければ飛ばす） ---------------------------------------

    def _update(self) -> None:
        """CppBuildの update（構成と生成ファイルの作り直し。約1秒）を、入力が前回から変わったときだけ行う。

        入力：管理ファイル・生成ファイルの中身、ファイルの一覧（CppBuildはソースを探して生成する）、
        依存先の同じもの、CppBuildの版。記録は build/ に置く（git の管理外。消えれば必ず行う）。
        """
        stamp = self.root / _cppbuild.BUILD_DIRECTORY / ".ecobuild-update"
        try:
            if stamp.is_file() and stamp.read_text(encoding="utf-8") == _fingerprint(self.root):
                return
        except OSError:
            pass
        _cppbuild.update(self.root)
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(_fingerprint(self.root), encoding="utf-8")  # 作り直した後の生成ファイルで記録する

    # 依存先 ------------------------------------------------------------------------

    def link(self, url: str, *, project: str | None, shared: bool) -> LinkResult:
        target = project or self.module.config.projects.library
        name = _cppbuild.link(self.root, target, url, shared=shared)
        revision = next(s.revision for s in _cppbuild.git_sources(self.root) if s.name == name)
        return LinkResult(name, url, revision, (target,))

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
            clone = Git(source.directory, command=COMMAND)
            head = clone.rev_parse("HEAD")
            branch = clone.current_branch()
            if branch is not None and ws.is_workspace_branch(branch):
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
                                hint=f"依存先：{'、'.join(names) or 'なし'}（{COMMAND} deps list）")
        return source

    def _dependency_state(self, source) -> DependencyState:
        directory = Path(source.directory)
        if not (directory / ".git").exists():
            return DependencyState(source.name, source.url, source.revision, None, "missing")
        clone = Git(directory, command=COMMAND)
        head = clone.rev_parse("HEAD")
        branch = clone.current_branch()
        if branch is not None and ws.is_workspace_branch(branch):
            state = "working"
        elif not clone.working_tree().clean:
            state = "modified"
        else:
            state = "aligned" if head == source.revision else "differs"
        return DependencyState(source.name, source.url, source.revision, head, state, branch)
