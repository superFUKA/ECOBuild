"""モジュール：ECOBuildの管理単位（GitHubリポジトリ＋CppBuildのSolution）。

作業の進め方（作業空間・ブランチ・PR・最新化）は ecowork.Repository が受け持つ。
Moduleはそれに、ecobuild.toml とCppBuildの処理（Solutionの作成・依存先・生成ファイル・ビルド）を組み合わせる。
"""

from __future__ import annotations

import re
from pathlib import Path

from ecowork import Hooks, Repository, WorkError
from ecowork import github as _github
from ecowork import workspace as ws
from ecowork.git import Git

from . import _cppbuild
from . import config as _config
from .errors import EcoBuildError, ErrorCode
from .results import BuildResult, DependencyChange, ModuleCreated, RunResult, SyncResult, TestCaseResult, TestResult

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

    def build(self, *, project: str | None = None, configuration: str = "Debug") -> BuildResult:
        outcome = _cppbuild.build(self.root, project=project, configuration=configuration)
        return BuildResult(project, configuration, tuple(Path(a).as_posix() for a in outcome.artifacts))

    def test(self, *, project: str | None = None, configuration: str = "Debug") -> TestResult:
        outcome = _cppbuild.test(self.root, project=project, configuration=configuration)
        cases = tuple(TestCaseResult(c.name, c.status) for c in outcome.cases)
        count = lambda status: sum(1 for c in cases if c.status == status)  # noqa: E731
        failed = len(cases) - count("passed") - count("skipped")
        return TestResult(project, configuration, count("passed"), failed, count("skipped"), cases)

    def run(self, *, project: str | None = None, configuration: str = "Debug", arguments: str = "") -> RunResult:
        outcome = _cppbuild.run(self.root, project=project, configuration=configuration, arguments=arguments)
        last = outcome.processes[-1] if outcome.processes else None
        return RunResult(project, configuration, 0 if last is None else last.returncode,
                         "" if last is None else last.output)

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
