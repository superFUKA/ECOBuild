"""モジュール：ECOBuildの管理単位（GitHubリポジトリ）。

作業の進め方（作業空間・ブランチ・PR・最新化）は ecowork.Repository が受け持つ。
言語ごとの処理（ビルド・Project・ファイル・依存先・生成ファイル）は、モジュールの型（module_type）が受け持つ。
Moduleはそれらを、ecobuild.toml と作業の流れの約束（ファイルを変える操作は作業空間でだけ等）でつなぐ。
"""

from __future__ import annotations

import re
from pathlib import Path

from ecowork import Hooks, Repository, WorkError
from ecowork import github as _github
from ecowork import workspace as ws

from . import _docs
from . import config as _config
from . import module_type as _module_type
from .errors import EcoBuildError, ErrorCode
from .fsutil import remove_tree
from .results import (BuildResult, CheckItem, CheckReport, CiInitResult, DependencyChange, DependencyState,
                      FilesChanged, LinkResult, ModuleCloned, ModuleCreated, ProfileList, RunResult, SyncResult,
                      TestResult)

COMMAND = "ecobuild"

_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")

GITIGNORE = """\
# ECOBuild
ecobuild.local.toml
"""


class _TypeHooks(Hooks):
    """作業の流れの途中で、モジュールの型に手元（依存先・生成ファイル）をそろえさせる。"""

    def __init__(self, module: "Module"):
        self._module = module

    def after_sync(self, repository: Repository) -> tuple[tuple[DependencyChange, ...], bool]:
        return self._module._after_sync()

    def after_switch(self, repository: Repository) -> None:
        # 切り替えた先の記録に、手元をそろえる（作業版・変更のある依存先は型が触らない）。
        self._module._after_sync()

    def before_submit(self, repository: Repository) -> None:
        self._module._check_generated_files()


class Module:
    def __init__(self, root: Path, module_config: _config.ModuleConfig, *, github: _github.GitHub | None = None):
        self.root = Path(root)
        self.config = module_config
        self.repository = Repository(self.root, github=github, default_base=module_config.default_base,
                                     command=COMMAND, hooks=_TypeHooks(self))
        self.type = _module_type.load(module_config.type)(self)

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
        type: str = "cpp",
        github: _github.GitHub | None = None,
    ) -> "Module":
        """GitHubリポジトリを作り、型が用意する中身と共に初回コミットをpushする。

        githubは試験でGitHubへの接続を差し替えるためのもの。
        """
        if not _NAME.fullmatch(name):
            raise EcoBuildError(
                ErrorCode.INVALID_CONFIG,
                f"モジュール名 {name!r} は使えません。",
                hint="英字で始まり、英数字と _ だけからなる名前にしてください。",
            )
        type_class = _module_type.load(type)
        module_config = type_class.new_config(name, app=app)

        def populate(root: Path) -> None:
            _config.save(module_config, root / _config.FILE_NAME)
            (root / ".gitignore").write_text(GITIGNORE + _with_gap(type_class.gitignore()),
                                             encoding="utf-8", newline="\n")
            if type_class.gitattributes():
                (root / ".gitattributes").write_text(type_class.gitattributes(), encoding="utf-8", newline="\n")
            (root / "README.md").write_text(_docs.readme(module_config, type_class), encoding="utf-8", newline="\n")
            (root / "AGENTS.md").write_text(_docs.agents(module_config, type_class), encoding="utf-8", newline="\n")
            type_class.populate(root, module_config)

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
            remove_tree(repository.root)  # 今cloneしたもの
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

    def status(self, *, fetch: bool = False) -> ws.Status:
        return self.repository.status(fetch=fetch)

    def tasks(self, *, closed: bool = False) -> list[ws.TaskSummary]:
        return self.repository.tasks(closed=closed)

    def task_status(self, number: int | None = None) -> ws.TaskStatus:
        return self.repository.task_status(number)

    def edit_task(self, number: int, *, title: str | None = None, body: str | None = None) -> ws.Task:
        return self.repository.edit_task(number, title=title, body=body)

    def close_task(self, number: int, *, not_planned: bool = False) -> ws.Task:
        return self.repository.close_task(number, not_planned=not_planned)

    def reopen_task(self, number: int) -> ws.Task:
        return self.repository.reopen_task(number)

    def review(self, number: int) -> ws.ReviewResult:
        """他人のPRを手元に取り出す。依存先・生成ファイルもそのPRの記録に合わせる。"""
        result = self.repository.review(number)
        self._after_sync()
        return result

    def end_review(self) -> ws.ReviewResult:
        result = self.repository.end_review()
        self._after_sync()
        return result

    def log(self, *, count: int = 20, paths: tuple[str, ...] = (), all_branches: bool = False) -> list[ws.LogEntry]:
        return self.repository.log(count=count, paths=paths, all_branches=all_branches)

    def show(self, revision: str = "HEAD") -> str:
        return self.repository.show(revision)

    def diff(self, paths: tuple[str, ...] = (), *, staged: bool = False, base: bool = False) -> str:
        return self.repository.diff(paths, staged=staged, base=base)

    def blame(self, path: str) -> str:
        return self.repository.blame(path)

    def revert(self, number: int) -> ws.RevertResult:
        return self.repository.revert(number)

    def ignore(self, *patterns: str) -> tuple[str, ...]:
        return self.repository.ignore(*patterns)

    def create_release(self, tag: str, *, title: str = "", notes: str = "", target: str | None = None):
        return self.repository.create_release(tag, title=title, notes=notes, target=target)

    def releases(self):
        return self.repository.releases()

    def start_task_in(self, number: int, directory: Path | str, *, base: str | None = None) -> "Module":
        """作業空間を専用のcloneで作り（I-007）、依存先と生成ファイルを用意する。"""
        repository = self.repository.clone_workspace(number, directory, base=base)
        module = Module.find(repository.root, github=self.repository.github)
        module._after_sync()
        return module

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
        """GitHubの最新を取り込み、手元（依存先・生成ファイル）をそろえる。

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
            if any(self.type.is_generated(p) for p in conflicted):
                error.hint = (f"{error.hint}\n{self.type.generated_note}は直さなくて構いません。"
                              f"{COMMAND} sync continue で管理ファイルから作り直します。")
            raise

    def continue_sync(self) -> SyncResult:
        """衝突を解決した後、止まっている取り込みを完了し、手元をそろえる。"""
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

    # ビルド（型） -----------------------------------------------------------------

    def project_at(self, path: Path | str) -> str | None:
        """pathが属するProjectの名前。どのProjectにも属さなければNone（全体が対象）。"""
        return self.type.project_at(Path(path))

    def executable_at(self, path: Path | str) -> str | None:
        """run の既定：pathが実行ファイルのProjectの中ならそれ、それ以外はNone（唯一の実行ファイル）。"""
        return self.type.executable_at(Path(path))

    def build(self, *, project: str | None = None, configuration: str = "", profile: str | None = None,
              action: str = "build") -> BuildResult:
        """build・clean・rebuild。configurationを省略すると、名前付きビルド設定（なければ型の既定）の構成。"""
        options, name = self.build_options(configuration, profile)
        result = self.type.build(project, options, action)
        return BuildResult(result.project, result.configuration, result.artifacts, name, result.action)

    def test(self, *, project: str | None = None, configuration: str = "", profile: str | None = None) -> TestResult:
        options, _ = self.build_options(configuration, profile)
        return self.type.test(project, options)

    def run(self, *, project: str | None = None, configuration: str = "", profile: str | None = None,
            arguments: str = "") -> RunResult:
        options, _ = self.build_options(configuration, profile)
        return self.type.run(project, options, arguments)

    # 名前付きビルド設定 ---------------------------------------------------------

    def build_options(self, configuration: str = "", profile: str | None = None):
        """使うビルド設定と、その名前。profileを省略すると、このPCで選んだ設定（ecobuild profile use）。"""
        name = profile or _config.load_local(self.root).get("profile")
        selected = None
        if name:
            if name not in self.config.profiles:
                raise EcoBuildError(ErrorCode.PROFILE_NOT_FOUND, f"ビルド設定 {name} はありません。",
                                    hint=f"{COMMAND} profile list で一覧、{COMMAND} profile add で追加できます。")
            selected = self.config.profiles[name]
        return self.type.build_options(selected, configuration), name

    def profiles(self) -> ProfileList:
        return ProfileList(dict(self.config.profiles), _config.load_local(self.root).get("profile"))

    def add_profile(self, name: str, profile: _config.Profile) -> ProfileList:
        self.require_workspace("ビルド設定の追加")
        if not _NAME.fullmatch(name):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"ビルド設定の名前 {name!r} は使えません。",
                                hint="英字で始まり、英数字と _ だけからなる名前にしてください。")
        self.type.validate_profile(profile)
        self._save_config(self.config.with_profiles({**self.config.profiles, name: profile}))
        return self.profiles()

    def remove_profile(self, name: str) -> ProfileList:
        self.require_workspace("ビルド設定の削除")
        if name not in self.config.profiles:
            raise EcoBuildError(ErrorCode.PROFILE_NOT_FOUND, f"ビルド設定 {name} はありません。")
        self._save_config(self.config.with_profiles({k: v for k, v in self.config.profiles.items() if k != name}))
        if _config.load_local(self.root).get("profile") == name:
            self.use_profile(None)
        return self.profiles()

    def use_profile(self, name: str | None) -> ProfileList:
        """このPCで使うビルド設定を選ぶ（Noneで選択を外し、型の既定に戻す）。"""
        if name is not None and name not in self.config.profiles:
            raise EcoBuildError(ErrorCode.PROFILE_NOT_FOUND, f"ビルド設定 {name} はありません。",
                                hint=f"{COMMAND} profile list で一覧を確認してください。")
        local = _config.load_local(self.root)
        local["profile"] = name
        _config.save_local(self.root, local)
        return self.profiles()

    # Project・ファイル（型） ---------------------------------------------------------

    def projects(self) -> tuple:
        return self.type.projects()

    def add_project(self, name: str, kind: str) -> FilesChanged:
        self.require_workspace("Projectの追加")
        if not _NAME.fullmatch(name):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"Project名 {name!r} は使えません。",
                                hint="英字で始まり、英数字と _ だけからなる名前にしてください。")
        return self.type.add_project(name, kind)

    def remove_project(self, name: str) -> FilesChanged:
        self.require_workspace("Projectの削除")
        return self.type.remove_project(name)

    def set_pch(self, project: str, *, enable: bool = True) -> FilesChanged:
        self.require_workspace("PCHの設定")
        return self.type.set_pch(project, enable=enable)

    def add_file(self, path: Path | str, *, test: bool = True) -> FilesChanged:
        """Projectにファイルを足す（テストを一緒に作るか等は型が決める）。"""
        self.require_workspace("ファイルの追加")
        return self.type.add_file(Path(path), test=test)

    def remove_file(self, path: Path | str, *, test: bool = True) -> FilesChanged:
        self.require_workspace("ファイルの削除")
        return self.type.remove_file(Path(path), test=test)

    def move_file(self, source: Path | str, destination: Path | str, *, test: bool = True) -> FilesChanged:
        self.require_workspace("ファイルの移動")
        return self.type.move_file(Path(source), Path(destination), test=test)

    # 依存先（型） -----------------------------------------------------------------

    def link(self, repository: str, *, project: str | None = None, shared: bool = False) -> LinkResult:
        """GitHubにあるモジュール（「名前」か「所有者/名前」）を依存先にする。"""
        self.require_workspace("依存先のリンク")
        url = self.repository.github.get_repository(repository).clone_url
        return self.type.link(url, project=project, shared=shared)

    def unlink(self, name: str) -> LinkResult:
        self.require_workspace("依存先のリンクの解除")
        return self.type.unlink(name)

    def dependencies(self) -> tuple[DependencyState, ...]:
        return self.type.dependencies()

    def update_dependencies(self, name: str | None = None) -> tuple[DependencyChange, ...]:
        """依存先の記録を、GitHubの最新にする（I-018）。"""
        self.require_workspace("依存先の更新")
        return self.type.update_dependencies(name)

    def sync_dependencies(self) -> tuple[DependencyChange, ...]:
        """手元の依存先を記録の版に合わせる（作業版・変更のあるものは触らない）。"""
        return self.type.sync_dependencies()

    # 文書・CI・確認 -------------------------------------------------------------

    def write_agents(self) -> FilesChanged:
        """AGENTS.md（エージェント向けの使い方）を作り直す。"""
        self.require_workspace("AGENTS.md の作成")
        (self.root / "AGENTS.md").write_text(_docs.agents(self.config, type(self.type)), encoding="utf-8",
                                             newline="\n")
        return FilesChanged("agent init", ("AGENTS.md",))

    def write_ci(self) -> CiInitResult:
        """GitHub Actions のワークフロー（中身は型が用意する）を作る。

        非公開の依存先は、CIの GITHUB_TOKEN では取得できない。その依存先を返す（案内に使う）。
        """
        self.require_workspace("CIの設定の作成")
        workflow = self.type.ci_workflow(self.config)
        if workflow is None:
            raise self.type.not_supported("CI")
        path = self.root / _docs.CI_WORKFLOW
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(workflow, encoding="utf-8", newline="\n")
        private = []
        for dependency in self.type.dependencies():
            name = dependency.url.removesuffix(".git").split("github.com/")[-1]
            try:
                if self.repository.github.is_private(name):
                    private.append(dependency.name)
            except Exception:  # GitHub以外・見つからない等は案内しない
                continue
        return CiInitResult(_docs.CI_WORKFLOW, tuple(private))

    def remove_ci(self) -> FilesChanged:
        """CI（ecobuild ci init で作ったワークフロー）をやめる。"""
        self.require_workspace("CIの設定の削除")
        path = self.root / _docs.CI_WORKFLOW
        if not path.is_file():
            raise EcoBuildError(ErrorCode.FILE_NOT_FOUND, f"{_docs.CI_WORKFLOW} はありません。")
        path.unlink()
        return FilesChanged("ci remove", (_docs.CI_WORKFLOW,))

    def ci_runs(self, *, pull_request: int | None = None, limit: int = 5) -> list:
        return self.repository.ci_runs(pull_request=pull_request, limit=limit)

    def ci_failed_log(self, run_id: int | None = None) -> tuple[int, str]:
        return self.repository.ci_failed_log(run_id)

    def ci_rerun(self, run_id: int | None = None, *, failed_only: bool = False) -> int:
        return self.repository.ci_rerun(run_id, failed_only=failed_only)

    def set_secret(self, name: str, value: str) -> str:
        return self.repository.set_secret(name, value)

    def secrets(self) -> list[str]:
        return self.repository.secrets()

    def ci_dispatch(self) -> str:
        """今いるブランチで、ECOBuildのCIを手動で実行する。"""
        return self.repository.ci_dispatch(Path(_docs.CI_WORKFLOW).name)

    def check(self, *, build: bool = True) -> CheckReport:
        """PRを出す前の確認：生成ファイル・衝突の印・ビルド・テスト。失敗があれば check_failed。

        コミットの前に使ってよい：生成ファイルは最新にし、未コミットなら知らせるだけ（コミットは task submit が確かめる）。
        """
        items = []
        try:
            self.type.refresh()
            pending = self._uncommitted_managed_files()
            items.append(CheckItem("generated", True, f"最新です（未コミット {len(pending)} ファイル。"
                                                      f"{COMMAND} task add --all でコミットに含めてください）" if pending else ""))
        except EcoBuildError as error:
            items.append(CheckItem("generated", False, error.message))
        git = self.repository.git
        workspace = self.current_workspace()
        markers = git.conflict_markers("HEAD")
        if workspace is not None and git.rev_parse(f"origin/{workspace.base}"):
            markers += git.conflict_markers(f"origin/{workspace.base}...HEAD")
        items.append(CheckItem("conflict_markers", not markers, ", ".join(dict.fromkeys(markers))))
        if build:
            for name, action in (("build", lambda: self.build()), ("test", lambda: self.test())):
                try:
                    result = action()
                    detail = f"成功 {result.passed}" if name == "test" else ""
                    items.append(CheckItem(name, True, detail))
                except EcoBuildError as error:
                    if error.code == ErrorCode.NOT_SUPPORTED:
                        continue  # ビルド・テストのない型
                    items.append(CheckItem(name, False, error.message))
                    break
        report = CheckReport(tuple(items))
        if not report.ok:
            raise EcoBuildError(ErrorCode.CHECK_FAILED, "確認で問題が見つかりました：" +
                                "、".join(i.name for i in items if not i.ok),
                                hint=f"内容を直して、もう一度 {COMMAND} check を実行してください。",
                                details=[{"name": i.name, "ok": i.ok, "detail": i.detail} for i in items])
        return report

    # 内部 -----------------------------------------------------------------

    def _save_config(self, module_config: _config.ModuleConfig) -> None:
        _config.save(module_config, self.root / _config.FILE_NAME)
        self.config = module_config

    @staticmethod
    def _sync_result(result: ws.SyncResult) -> SyncResult:
        dependencies, regenerated = result.extra if result.extra is not None else ((), False)
        return SyncResult(result.branch, result.merged, dependencies, regenerated)

    def _after_sync(self) -> tuple[tuple[DependencyChange, ...], bool]:
        return self.type.prepare()

    def _uncommitted_managed_files(self) -> list[str]:
        tree = self.repository.git.working_tree()
        return sorted({p for p in (*tree.staged, *tree.unstaged, *tree.untracked) if self.type.is_managed(p)})

    def _regenerate_conflicted_files(self) -> bool:
        """衝突した生成ファイルを、（衝突の解決済みの）管理ファイルから作り直して登録する。"""
        git = self.repository.git
        conflicted = git.working_tree().conflicted
        generated = [p for p in conflicted if self.type.is_generated(p)]
        if not generated or any(self.type.is_managed(p) and p not in generated for p in conflicted):
            return False  # 管理ファイルの衝突が残っていると作り直せない
        git.run("checkout", "--ours", "--", *generated)
        self.type.refresh()
        git.add(tuple(generated))
        return True

    def _check_generated_files(self) -> None:
        """生成ファイルを作り直し、生成・管理ファイルに未コミットの変更があれば止める（task submit の前）。"""
        if not self.type.refresh():
            return
        changed = self._uncommitted_managed_files()
        if changed:
            raise EcoBuildError(
                ErrorCode.GENERATED_FILES_OUTDATED,
                f"{self.type.generated_note or '生成ファイル'}・管理ファイルがコミットされていません。",
                hint=f"{COMMAND} task add --all でステージし、{COMMAND} task commit でコミットしてから再実行してください。",
                details=changed,
            )

    def __repr__(self) -> str:
        return f"Module({self.name!r}, {str(self.root)!r})"


def _with_gap(text: str) -> str:
    return "\n" + text if text else ""
