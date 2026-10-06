"""モジュール：ECOBuildの管理単位（GitHubリポジトリ＋CppBuildのSolution）。

作業の進め方（作業空間・ブランチ・PR・最新化）は ecowork.Repository が受け持つ。
Moduleはそれに、ecobuild.toml とCppBuildの処理（Solutionの作成・依存先・生成ファイル・ビルド）を組み合わせる。
"""

from __future__ import annotations

import os
import re
import shutil
import stat
from pathlib import Path

from ecowork import Hooks, Repository, WorkError
from ecowork import github as _github
from ecowork import workspace as ws
from ecowork.git import Git

from . import _cppbuild
from . import config as _config
from .errors import EcoBuildError, ErrorCode
from .results import BuildResult, DependencyChange, DependencyState, FilesChanged, LinkResult, ModuleCloned, ModuleCreated, ProfileList, RunResult, SyncResult, TestCaseResult, TestResult

COMMAND = "ecobuild"

_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")

GITIGNORE = """\
# ECOBuild
/deps/
/build/
ecobuild.local.toml

# CppBuildの中間ファイル・成果物
.cppbuild/output/
"""


# CppBuildは生成・管理ファイルをLFで書く。gitの改行変換（Windowsのcore.autocrlf=true等）で
# CRLFにされると、生成し直すたびに「変更あり」になるため、LFに固定する。
GITATTRIBUTES = """\
# ECOBuild：CppBuildの生成ファイル・管理ファイルの改行をLFに固定する
CMakeLists.txt text eol=lf
*.cmake text eol=lf
.cppbuild/** text eol=lf
ecobuild.toml text eol=lf
"""


def _remove_tree(path: Path) -> None:
    """gitの読み取り専用ファイル（Windows）も含めて削除する。"""
    def retry(function, target, _):
        os.chmod(target, stat.S_IWRITE)
        function(target)
    shutil.rmtree(path, onerror=retry)


class _CppBuildHooks(Hooks):
    """作業の流れの途中で、CppBuildの依存先と生成ファイルを扱う。"""

    def __init__(self, module: "Module"):
        self._module = module

    def after_sync(self, repository: Repository) -> tuple[tuple[DependencyChange, ...], bool]:
        return self._module._after_sync()

    def before_submit(self, repository: Repository) -> None:
        self._module._check_generated_files()


class Module:
    def __init__(self, root: Path, module_config: _config.ModuleConfig, *, github: _github.GitHub | None = None):
        self.root = Path(root)
        self.config = module_config
        self.repository = Repository(self.root, github=github, default_base=module_config.default_base,
                                     command=COMMAND, hooks=_CppBuildHooks(self))

    @property
    def name(self) -> str:
        return self.config.name

    @classmethod
    def find(cls, path: Path | str = ".", *, github: _github.GitHub | None = None) -> "Module":
        """pathから上へecobuild.tomlを探し、最も近いモジュールを返す（I-027）。"""
        root = _config.find_root(Path(path))
        return cls(root, _config.load(root / _config.FILE_NAME), github=github)

    @classmethod
    def create(
        cls,
        name: str,
        *,
        directory: Path | str = ".",
        description: str = "",
        public: bool = False,
        app: bool = False,
        owner: str | None = None,
        github: _github.GitHub | None = None,
    ) -> "Module":
        """GitHubリポジトリとCppBuildのSolutionを作り、初回コミットをpushする。

        githubは試験でGitHubへの接続を差し替えるためのもの。
        """
        if not _NAME.fullmatch(name):
            raise EcoBuildError(
                ErrorCode.INVALID_CONFIG,
                f"モジュール名 {name!r} は使えません。",
                hint="英字で始まり、英数字と _ だけからなる名前にしてください。",
            )
        module_config = _config.ModuleConfig.for_new_module(name, app=app)

        def populate(root: Path) -> None:
            _config.save(module_config, root / _config.FILE_NAME)
            (root / ".gitignore").write_text(GITIGNORE, encoding="utf-8", newline="\n")
            (root / ".gitattributes").write_text(GITATTRIBUTES, encoding="utf-8", newline="\n")
            _cppbuild.create_module_solution(root, name, module_config.projects)
            _cppbuild.update(root)

        repository = Repository.create(
            name, directory=directory, description=description, private=not public, owner=owner,
            populate=populate, message="ECOBuildでモジュールを作成", github=github,
            default_base=module_config.default_base, command=COMMAND,
        )
        return cls(repository.root, module_config, github=repository.github)

    @classmethod
    def clone(
        cls, name: str, *, directory: Path | str = ".", github: _github.GitHub | None = None,
    ) -> tuple["Module", tuple[DependencyChange, ...]]:
        """GitHubにあるモジュールをcloneし、依存先と生成ファイルを用意する（sync と同じ）。

        name は「名前」（ログイン中のユーザーのもの）か「所有者/名前」。
        """
        repository = Repository.clone(name, directory=directory, github=github, command=COMMAND)
        if not (repository.root / _config.FILE_NAME).is_file():
            _remove_tree(repository.root)  # 今cloneしたもの
            raise EcoBuildError(
                ErrorCode.NOT_IN_MODULE,
                f"{name} はECOBuildのモジュールではありません（{_config.FILE_NAME} がありません）。",
                hint=f"ECOBuildで作ったリポジトリ（{COMMAND} new）を指定してください。",
            )
        module = cls.find(repository.root, github=repository.github)
        dependencies, _ = module._after_sync()
        return module, dependencies

    def cloned(self, dependencies: tuple[DependencyChange, ...]) -> ModuleCloned:
        return ModuleCloned(self.name, self.root, self.remote_url or "", self.project_names, dependencies)

    @property
    def remote_url(self) -> str | None:
        return self.repository.remote_url

    @property
    def project_names(self) -> tuple[str, ...]:
        projects = self.config.projects
        return tuple(p for p in (projects.library, projects.test, projects.app) if p is not None)

    def summary(self) -> ModuleCreated:
        return ModuleCreated(self.name, self.root, self.remote_url or "", self.project_names)

    # 作業の進め方（ecowork） ---------------------------------------------------

    def status(self) -> ws.Status:
        return self.repository.status()

    def branches(self) -> list[ws.Branch]:
        return self.repository.branches()

    def branch(self, name: str) -> ws.Branch:
        return self.repository.branch(name)

    def create_branch(self, name: str, *, base: str | None = None) -> ws.Branch:
        return self.repository.create_branch(name, base=base)

    def create_task(self, title: str, *, body: str = "") -> ws.Task:
        return self.repository.create_task(title, body=body)

    def task(self, number: int) -> ws.Task:
        return self.repository.task(number)

    def current_workspace(self) -> ws.Workspace | None:
        return self.repository.current_workspace()

    def require_workspace(self, action: str) -> ws.Workspace:
        return self.repository.require_workspace(action)

    def pull_request(self, number: int | None = None) -> ws.PullRequest:
        return self.repository.pull_request(number)

    def clean_workspaces(self, *, dry_run: bool = False) -> ws.CleanResult:
        return self.repository.clean_workspaces(dry_run=dry_run)

    def drop_workspace(self, number: int | None = None, *, close: bool = False, discard: bool = False,
                       dry_run: bool = False) -> ws.DropResult:
        return self.repository.drop_workspace(number, close=close, discard=discard, dry_run=dry_run)

    def sync(self) -> SyncResult:
        """GitHubの最新を取り込み、依存先の版と生成ファイルを最新にする。

        衝突したのが生成ファイルだけなら、管理ファイルから作り直して取り込みを完了する。
        """
        try:
            return self._sync_result(self.repository.sync())
        except WorkError as error:
            if error.code != ErrorCode.MERGE_CONFLICT or not self.repository.git.is_merging():
                raise
            if self._regenerate_conflicted_files() and not self.repository.git.working_tree().conflicted:
                return self.continue_sync()
            conflicted = self.repository.git.working_tree().conflicted
            error.details = list(conflicted)
            if any(_cppbuild.is_generated(p) for p in conflicted):
                error.hint = (f"{error.hint}\nCppBuildの生成ファイル（{'・'.join(_cppbuild.GENERATED_FILE_NAMES)}）は"
                              f"直さなくて構いません。{COMMAND} sync continue で管理ファイルから作り直します。")
            raise

    def continue_sync(self) -> SyncResult:
        """衝突を解決した後、止まっている取り込みを完了し、依存先の版と生成ファイルを最新にする。"""
        self._regenerate_conflicted_files()
        return self._sync_result(self.repository.continue_sync())

    def abort_sync(self) -> None:
        self.repository.abort_sync()

    def stash(self) -> ws.StashResult:
        return self.repository.stash()

    def stash_pop(self) -> ws.StashResult:
        return self.repository.stash_pop()

    def stash_drop(self) -> ws.StashResult:
        return self.repository.stash_drop()

    def stashes(self) -> tuple[str, ...]:
        return self.repository.stashes()

    def restore(self, *paths: str, staged: bool = False) -> ws.RestoreResult:
        return self.repository.restore(*paths, staged=staged)

    # ビルド ---------------------------------------------------------------

    def project_at(self, path: Path | str) -> str | None:
        """pathが属するProjectの名前。どのProjectにも属さなければNone（全体が対象）。"""
        return _cppbuild.project_at(self.root, Path(path))

    def executable_at(self, path: Path | str) -> str | None:
        """run の既定：pathが実行ファイルのProjectの中ならそれ、それ以外はNone（唯一の実行ファイル）。"""
        project = self.project_at(path)
        executables = {p.name for p in self.projects() if p.kind == "executable"}
        return project if project in executables else None

    def build(self, *, project: str | None = None, configuration: str = "", profile: str | None = None,
              action: str = "build") -> BuildResult:
        """build・clean・rebuild。configurationを省略すると、名前付きビルド設定（なければDebug）の構成。"""
        options, name = self.build_options(configuration, profile)
        outcome = _cppbuild.build(self.root, project=project, options=options, action=action)
        return BuildResult(project, options.configuration, tuple(Path(a).as_posix() for a in outcome.artifacts),
                           name, action)

    def test(self, *, project: str | None = None, configuration: str = "", profile: str | None = None) -> TestResult:
        options, _ = self.build_options(configuration, profile)
        outcome = _cppbuild.test(self.root, project=project, options=options)
        cases = tuple(TestCaseResult(c.name, c.status) for c in outcome.cases)
        count = lambda status: sum(1 for c in cases if c.status == status)  # noqa: E731
        failed = len(cases) - count("passed") - count("skipped")
        return TestResult(project, options.configuration, count("passed"), failed, count("skipped"), cases)

    def run(self, *, project: str | None = None, configuration: str = "", profile: str | None = None,
            arguments: str = "") -> RunResult:
        options, _ = self.build_options(configuration, profile)
        outcome = _cppbuild.run(self.root, project=project, options=options, arguments=arguments)
        last = outcome.processes[-1] if outcome.processes else None
        return RunResult(project, options.configuration, 0 if last is None else last.returncode,
                         "" if last is None else last.output)

    # 名前付きビルド設定 ---------------------------------------------------------

    def build_options(self, configuration: str = "", profile: str | None = None
                      ) -> tuple[_cppbuild.BuildOptions, str | None]:
        """使うビルド設定。profileを省略すると、このPCで選んだ設定（ecobuild profile use）。"""
        name = profile or _config.load_local(self.root).get("profile")
        selected = _config.Profile()
        if name:
            if name not in self.config.profiles:
                raise EcoBuildError(ErrorCode.PROFILE_NOT_FOUND, f"ビルド設定 {name} はありません。",
                                    hint=f"{COMMAND} profile list で一覧、{COMMAND} profile add で追加できます。")
            selected = self.config.profiles[name]
        return _cppbuild.BuildOptions(configuration or selected.configuration, selected.parallel,
                                      selected.shared), name

    def profiles(self) -> ProfileList:
        return ProfileList(dict(self.config.profiles), _config.load_local(self.root).get("profile"))

    def add_profile(self, name: str, profile: _config.Profile) -> ProfileList:
        if not _NAME.fullmatch(name):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"ビルド設定の名前 {name!r} は使えません。",
                                hint="英字で始まり、英数字と _ だけからなる名前にしてください。")
        if profile.configuration not in _config.CONFIGURATIONS:
            raise EcoBuildError(ErrorCode.INVALID_CONFIGURATION, f"構成 {profile.configuration} はありません。",
                                hint=f"{'・'.join(_config.CONFIGURATIONS)} のどれかを指定してください。")
        if profile.parallel < 1:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "並列数は1以上にしてください。")
        self._save_config(self.config.with_profiles({**self.config.profiles, name: profile}))
        return self.profiles()

    def remove_profile(self, name: str) -> ProfileList:
        if name not in self.config.profiles:
            raise EcoBuildError(ErrorCode.PROFILE_NOT_FOUND, f"ビルド設定 {name} はありません。")
        self._save_config(self.config.with_profiles({k: v for k, v in self.config.profiles.items() if k != name}))
        if _config.load_local(self.root).get("profile") == name:
            self.use_profile(None)
        return self.profiles()

    def use_profile(self, name: str | None) -> ProfileList:
        """このPCで使うビルド設定を選ぶ（Noneで選択を外し、Debugに戻す）。"""
        if name is not None and name not in self.config.profiles:
            raise EcoBuildError(ErrorCode.PROFILE_NOT_FOUND, f"ビルド設定 {name} はありません。",
                                hint=f"{COMMAND} profile list で一覧を確認してください。")
        local = _config.load_local(self.root)
        local["profile"] = name
        _config.save_local(self.root, local)
        return self.profiles()

    # Project・ファイル ---------------------------------------------------------

    @property
    def library_header(self) -> str:
        library = self.config.projects.library
        return f"{library}/{library}.h"

    def projects(self) -> tuple[_cppbuild.ProjectSummary, ...]:
        return _cppbuild.list_projects(self.root)

    def add_project(self, name: str, kind: str) -> FilesChanged:
        if not _NAME.fullmatch(name):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"Project名 {name!r} は使えません。",
                                hint="英字で始まり、英数字と _ だけからなる名前にしてください。")
        files = _cppbuild.add_project(self.root, name, kind, library=self.config.projects.library,
                                      library_header=self.library_header)
        return FilesChanged("project add", files, name)

    def remove_project(self, name: str) -> FilesChanged:
        projects = self.config.projects
        if name in (projects.library, projects.test, projects.app):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                                f"Project {name} は {_config.FILE_NAME} の [projects] にある基本のProjectです。",
                                hint="基本のProject（ライブラリ・テスト・実行ファイル）は外せません。")
        directory = _cppbuild.project_root(self.root, name)
        _cppbuild.remove_project(self.root, name)
        if directory.is_dir():
            _remove_tree(directory)
        return FilesChanged("project remove", (directory.relative_to(self.root).as_posix(),), name)

    def set_pch(self, project: str, *, enable: bool = True) -> FilesChanged:
        header = _cppbuild.set_pch(self.root, project, enable=enable)
        return FilesChanged("pch" if enable else "pch off", (header,) if header else (), project)

    def add_file(self, path: Path | str, *, test: bool = True) -> FilesChanged:
        """Projectにファイルを足す。ライブラリのソースなら、テスト用Projectの同じ構成の場所にテストも足す（I-014）。"""
        project, relative = self._in_project(path)
        header = self._header_for(project, relative)
        added = [_cppbuild.add_file(self.root, project, relative, replacements={"header": header})]
        mirror = self._test_mirror(project, relative)
        if test and mirror is not None:
            added.append(_cppbuild.add_file(self.root, self.config.projects.test, mirror, template="unit_test",
                                            replacements={"header": header, "suite": Path(relative).stem}))
        return FilesChanged("file add", tuple(added), project)

    def remove_file(self, path: Path | str, *, test: bool = True) -> FilesChanged:
        project, relative = self._in_project(path)
        removed = [_cppbuild.remove_file(self.root, project, relative)]
        mirror = self._test_mirror(project, relative)
        test_root = None if mirror is None else _cppbuild.project_root(self.root, self.config.projects.test)
        if test and mirror is not None and (test_root / mirror).is_file():
            removed.append(_cppbuild.remove_file(self.root, self.config.projects.test, mirror))
        return FilesChanged("file remove", tuple(removed), project)

    def move_file(self, source: Path | str, destination: Path | str, *, test: bool = True) -> FilesChanged:
        project, relative = self._in_project(source)
        other, target = self._in_project(destination)
        if other != project:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "別のProjectへは移動できません。",
                                hint="移動先も同じProjectのディレクトリの中にしてください。")
        moved = list(_cppbuild.move_file(self.root, project, relative, target))
        mirror, mirror_target = self._test_mirror(project, relative), self._test_mirror(project, target)
        test_project = self.config.projects.test
        if test and mirror and mirror_target and (_cppbuild.project_root(self.root, test_project) / mirror).is_file():
            moved += _cppbuild.move_file(self.root, test_project, mirror, mirror_target)
        return FilesChanged("file move", tuple(moved), project)

    def _in_project(self, path: Path | str) -> tuple[str, str]:
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
        if project != self.config.projects.library or path.parts[:1] != ("src",) \
                or path.suffix.lower() not in _cppbuild.SOURCE_SUFFIXES:
            return None
        return path.with_name(f"{path.stem}Test{path.suffix}").as_posix()

    def _save_config(self, module_config: _config.ModuleConfig) -> None:
        _config.save(module_config, self.root / _config.FILE_NAME)
        self.config = module_config

    # 内部 -----------------------------------------------------------------

    @staticmethod
    def _sync_result(result: ws.SyncResult) -> SyncResult:
        dependencies, regenerated = result.extra if result.extra is not None else ((), False)
        return SyncResult(result.branch, result.merged, dependencies, regenerated)

    def _after_sync(self) -> tuple[tuple[DependencyChange, ...], bool]:
        if not (self.root / _cppbuild.CONFIG_DIRECTORY).is_dir():
            return (), False
        dependencies = self._sync_dependencies()
        _cppbuild.update(self.root)
        return dependencies, True

    def _sync_dependencies(self) -> tuple[DependencyChange, ...]:
        """依存先を記録の版に合わせる。手元で変更・コミットしているものは触らない。"""
        fetched, sources = _cppbuild.fetch_dependencies(self.root)
        changes = []
        for source in sources:
            if source.name in fetched:
                changes.append(DependencyChange(source.name, "cloned"))
                continue
            clone = Git(source.directory, command=COMMAND)
            head = clone.rev_parse("HEAD")
            branch = clone.current_branch()
            if branch is not None:
                # 依存先の中で task start 等をした作業版（I-019）。記録の版へ切り替えない。
                changes.append(DependencyChange(source.name, "skipped", f"作業版です（{branch}）"))
                continue
            if head == source.revision:
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

    def _regenerate_conflicted_files(self) -> bool:
        """衝突した生成ファイルを、（衝突の解決済みの）管理ファイルから作り直して登録する。"""
        git = self.repository.git
        conflicted = git.working_tree().conflicted
        generated = [p for p in conflicted if _cppbuild.is_generated(p)]
        if not generated or any(_cppbuild.is_generated_or_managed(p) and p not in generated for p in conflicted):
            return False  # 管理ファイルの衝突が残っていると作り直せない
        git.run("checkout", "--ours", "--", *generated)
        _cppbuild.update(self.root)
        git.add(tuple(generated))
        return True

    # 依存先 -----------------------------------------------------------------

    def link(self, repository: str, *, project: str | None = None, shared: bool = False) -> LinkResult:
        """GitHubにあるモジュール（「名前」か「所有者/名前」）をリンクし、deps/ へcloneする。"""
        url = self.repository.github.get_repository(repository).clone_url
        target = project or self.config.projects.library
        name = _cppbuild.link(self.root, target, url, shared=shared)
        revision = next(s.revision for s in _cppbuild.git_sources(self.root) if s.name == name)
        return LinkResult(name, url, revision, (target,))

    def unlink(self, name: str) -> LinkResult:
        """依存先のリンクを外す。手元のcloneは、失われる変更がなければ消す。"""
        source = self._source(name)
        projects = _cppbuild.unlink(self.root, name)
        directory = Path(source.directory)
        removable = directory.is_dir() and self._dependency_state(source).state == "aligned"
        if removable:
            _remove_tree(directory)
        return LinkResult(name, source.url, source.revision, projects, removable)

    def dependencies(self) -> tuple[DependencyState, ...]:
        return tuple(self._dependency_state(s) for s in _cppbuild.git_sources(self.root))

    def update_dependencies(self, name: str | None = None) -> tuple[DependencyChange, ...]:
        """依存先の記録を、GitHubの最新にする（I-018）。手元のcloneも合わせ、生成ファイルを更新する。"""
        names = [name] if name else [s.name for s in _cppbuild.git_sources(self.root)]
        if name:
            self._source(name)
        updated = {}
        for each in names:
            before = self._source(each).revision
            after = _cppbuild.record_latest(self.root, each)
            updated[each] = (before, after)
        changes = []
        for change in self._sync_dependencies():
            if change.name not in updated:
                continue
            before, after = updated[change.name]
            note = "最新です" if before == after else f"{before[:7]} → {after[:7]}"
            changes.append(DependencyChange(change.name, change.action,
                                            note if change.reason is None else f"{note}（{change.reason}）"))
        _cppbuild.update(self.root)
        return tuple(changes)

    def sync_dependencies(self) -> tuple[DependencyChange, ...]:
        """手元の依存先を記録の版に合わせる（作業版・変更のあるものは触らない）。"""
        changes = self._sync_dependencies()
        _cppbuild.update(self.root)
        return changes

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
        if branch is not None:
            state = "working"
        elif not clone.working_tree().clean:
            state = "modified"
        else:
            state = "aligned" if head == source.revision else "differs"
        return DependencyState(source.name, source.url, source.revision, head, state, branch)

    def _check_generated_files(self) -> None:
        """CppBuildで生成し直し、生成・管理ファイルに未コミットの変更があれば止める。"""
        if not (self.root / _cppbuild.CONFIG_DIRECTORY).is_dir():
            return
        _cppbuild.update(self.root)
        tree = self.repository.git.working_tree()
        changed = sorted({p for p in (*tree.staged, *tree.unstaged, *tree.untracked)
                          if _cppbuild.is_generated_or_managed(p)})
        if changed:
            raise EcoBuildError(
                ErrorCode.GENERATED_FILES_OUTDATED,
                "CppBuildの生成ファイル・管理ファイルがコミットされていません。",
                hint=f"{COMMAND} add --all でステージし、{COMMAND} commit でコミットしてから再実行してください。",
                details=changed,
            )

    def __repr__(self) -> str:
        return f"Module({self.name!r}, {str(self.root)!r})"
