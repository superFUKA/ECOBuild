"""モジュール：ECOBuildの管理単位（GitHubリポジトリ）。

作業の進め方（作業空間・ブランチ・PR・最新化）は ecowork.Repository が受け持つ。
言語ごとの処理（ビルド・Project・ファイル・依存先・生成ファイル）は、モジュールの型（module_type）が受け持つ。
Moduleはそれらを、ecobuild.toml と作業の流れの約束（ファイルを変える操作は作業空間でだけ等）でつなぐ。
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import replace
from pathlib import Path

from ecotask.board import description as _board_description
from ecowork import Hooks, Repository, WorkError
from ecowork import github as _github
from ecowork import workspace as ws

from . import _docs
from . import clones as _clones
from . import config as _config
from . import module_type as _module_type
from .errors import EcoBuildError, ErrorCode
from .fsutil import remove_tree
from .results import (BuildResult, CheckItem, CheckReport, CiInitResult, CloneEntry, DependencyChange, DependencyState,
                      DependencyTree, FilesChanged, LinkResult, ModuleArchived, ModuleCloned, ModuleCreated,
                      ModuleDeleted, ModuleEntry, ModuleInfo, PrepareResult, ProfileList,
                      ProjectSummary, RunResult, SyncResult, TestResult)

COMMAND = "ecobuild"

_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")

GITIGNORE = """\
# ECOBuild
ecobuild.local.toml
"""


class _TypeHooks(Hooks):
    """作業の流れの途中で、モジュールの型に手元（依存先・生成ファイル）をそろえさせる。

    1つの Module（そのclone）に結び付く。別のcloneの Repository には渡さない（start_task_in を参照）。
    """

    def __init__(self, module: "Module"):
        self._module = module

    def after_sync(self, repository: Repository) -> PrepareResult:
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
                                     command=COMMAND, hooks=_TypeHooks(self),
                                     legacy_board=module_config.legacy_board)
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
        kind: str = "",
        project: str = "",
        owner: str | None = None,
        type: str = "cpp",
        github: _github.GitHub | None = None,
    ) -> "Module":
        """GitHubリポジトリを作り、型が用意する中身と共に初回コミットをpushする。タスク管理も準備する
        （できなければ知らせ、タスクを初めて記録するときにもう一度行う）。

        kind：最初に作るもの（型の new_kinds。C++：app＝実行ファイル〔既定〕・library＝ライブラリとテスト用・
        none＝作らない）。モジュールはリンクのための単位ではなく、中身は後から project add で足す。
        project：最初に作るProjectの名前（省略時はモジュール名。ライブラリならテスト用は <名前>Test）。
        githubは試験でGitHubへの接続を差し替えるためのもの。
        """
        if not _NAME.fullmatch(name):
            raise EcoBuildError(
                ErrorCode.INVALID_CONFIG,
                f"モジュール名 {name!r} は使えません。",
                hint="英字で始まり、英数字と _ だけからなる名前にしてください。",
            )
        type_class = _module_type.load(type)
        if kind and kind not in type_class.new_kinds:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"--kind {kind} は型 {type_class.name} では使えません。",
                                hint=f"使えるもの：{'・'.join(type_class.new_kinds)}" if type_class.new_kinds
                                else f"型 {type_class.name} は、最初に作るものを選べません。")
        if project:
            if not type_class.new_kinds or (kind or type_class.default_new_kind) == "none":
                raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "--project は、最初にProjectを作るときだけ使えます。",
                                    hint=f"型 {type_class.name} の --kind none では、Projectを作りません。"
                                    if type_class.new_kinds else f"型 {type_class.name} は、Projectを作りません。")
            if not _NAME.fullmatch(project):
                raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"Project名 {project!r} は使えません。",
                                    hint="英字で始まり、英数字と _ だけからなる名前にしてください。")
        module_config = type_class.new_config(name)

        def populate(root: Path) -> None:
            _config.save(module_config, root / _config.FILE_NAME)
            (root / ".gitignore").write_text(GITIGNORE + _with_gap(type_class.gitignore()),
                                             encoding="utf-8", newline="\n")
            if type_class.gitattributes():
                (root / ".gitattributes").write_text(type_class.gitattributes(), encoding="utf-8", newline="\n")
            (root / "README.md").write_text(_docs.readme(module_config, type_class), encoding="utf-8", newline="\n")
            (root / "AGENTS.md").write_text(_docs.agents(module_config, type_class), encoding="utf-8", newline="\n")
            type_class.populate(root, module_config, kind or None, project or None)

        repository = Repository.create(
            name, directory=directory, description=description, private=not public, owner=owner,
            populate=populate, message="ECOBuildでモジュールを作成", github=github,
            default_base=module_config.default_base, command=COMMAND,
        )
        module = cls(repository.root, module_config, github=repository.github)
        try:
            module.repository.prepare_tasks()
        except WorkError as error:
            module.repository.notices.append(f"タスク管理の準備ができませんでした（{error.message}）。"
                                             "タスクを初めて記録するときに、もう一度行います。")
        return module

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
                hint=f"ECOBuildで作ったリポジトリ（{COMMAND} module new）を指定してください。",
            )
        module = cls.find(repository.root, github=repository.github)
        dependencies, _ = module._after_sync()
        return module, dependencies

    @staticmethod
    def modules(owner: str | None = None, *, archived: bool | None = False,
                github: _github.GitHub | None = None) -> tuple[ModuleEntry, ...]:
        """GitHubにある、所有者（既定はログイン中のユーザー）のECOBuildのモジュール（ecobuild.toml があるリポジトリ）。
        archived：False＝アーカイブしていないもの、True＝アーカイブしたものだけ、None＝両方。新しく更新した順。"""
        github = github or _github.default()
        return tuple(ModuleEntry(r.full_name, r.url, _module_type_of(r.module_file), r.description, r.private,
                                 r.archived, r.updated)
                     for r in github.owner_repositories(owner)
                     if r.module_file is not None and (archived is None or r.archived == archived))

    @staticmethod
    def clones(*, fetch: bool = False, github: _github.GitHub | None = None) -> tuple[CloneEntry, ...]:
        """このPCにある、モジュールのclone（記録したもの）。fetch：GitHubの側も確かめる（まだあるか・アーカイブ・
        名前の変更）。GitHubのものでない origin は確かめない。"""
        entries = _clones.entries()
        if not fetch:
            return tuple(entries)
        github = github or _github.default()
        states: dict[str, tuple[str, str | None]] = {}
        for entry in entries:
            if entry.repository and entry.repository.casefold() not in states:
                states[entry.repository.casefold()] = _github_state(github, entry.repository)
        return tuple(replace(e, remote=states[e.repository.casefold()][0], moved_to=states[e.repository.casefold()][1])
                     if e.repository else e for e in entries)

    def own_clones(self) -> tuple[CloneEntry, ...]:
        """このPCにある、このモジュール（同じリポジトリ）のclone（記録したもの。ここも含む）。"""
        mine = _clones.identity(self.remote_url)
        if mine is None:
            return tuple(e for e in _clones.entries() if _clones.same(e.path, self.root))
        return tuple(e for e in _clones.entries() if e.exists and _clones.identity(e.url) == mine)

    def _workspace_paths(self) -> dict[int, Path]:
        """作業空間（task/<番号>）にいる、このモジュールのclone の場所（このPCの、記録したもの）。"""
        return {e.task: e.path for e in self.own_clones() if e.task is not None}

    def info(self) -> ModuleInfo:
        """このモジュールの情報。GitHubに問い合わせられなければ、公開・アーカイブは分からない（None）。"""
        github = self.repository.github
        repository, url, private, archived = "", self.remote_url or "", None, None
        try:
            repository = github.repository_name(self.root)
            found = github.get_repository(repository)
            url, archived, private = found.web_url, found.archived, github.is_private(repository)
        except WorkError as error:
            self.repository.notices.append(f"GitHubのリポジトリの情報を読めませんでした（{error.message}）。")
        try:
            dependencies = tuple(d.name for d in self.dependencies())
        except EcoBuildError as error:   # 管理ファイルが壊れている等。他の情報は出す
            dependencies = ()
            self.repository.notices.append(f"依存先を読めませんでした（{error.message}）。")
        return ModuleInfo(self.name, self.config.type, self.root, repository, url, private, archived,
                          self.config.default_base, self.project_names, dependencies, self.own_clones())

    @classmethod
    def archive(cls, name: str, *, archived: bool = True, github: _github.GitHub | None = None) -> ModuleArchived:
        """GitHubのモジュール（リポジトリ）をアーカイブ（読み取り専用）にする（archived=False：元に戻す）。
        タスク管理の情報は、元に戻したときにそのまま使えるように残す。既にその状態なら何もしない。"""
        github = github or _github.default()
        info = cls._module_repository(name, github)
        if info.archived != archived:
            github.archive_repository(info.full_name, archived=archived)
        return ModuleArchived(info.full_name, info.web_url, archived)

    @classmethod
    def delete(
        cls, name: str, *, clone: "Module | None" = None, remove_clone: bool = False, dry_run: bool = False,
        github: _github.GitHub | None = None,
    ) -> ModuleDeleted:
        """アーカイブしたモジュール（リポジトリ）を削除する。GitHubの機能で、90日以内なら元に戻せる。

        タスク管理の情報は消さずに閉じる（リポジトリを戻すと、ECOBuildが開き直して使う）。
        手元のclone：clone（今いる等。このモジュールのもの）と、このPCに記録した、このモジュールのcloneすべて
        （作業空間専用のcloneも）。remove_clone なら一緒に削除し、記録から外す（どれか1つにでもGitHubにない変更・
        コミット・退避があれば、何もせずに断る）。dry_run：確かめて、何をするかを返すだけ。
        """
        github = github or _github.default()
        info = cls._module_repository(name, github)
        if not info.archived:
            raise EcoBuildError(ErrorCode.NOT_ARCHIVED, f"{info.full_name} はアーカイブしていません。",
                                hint=f"削除する前に、{COMMAND} module archive {info.full_name} でアーカイブしてください"
                                     "（読み取り専用にし、使っていないことを確かめる段階です）。")
        if clone is not None and github.repository_name(clone.root) != info.full_name:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{clone.root} は {info.full_name} のcloneではありません。")
        found = ([clone] if clone is not None else []) + [
            c for c in cls._recorded_clones(info.full_name, github)
            if clone is None or not _clones.same(c.root, clone.root)]
        if remove_clone:
            cls._check_nothing_unpushed_in(found)
        issues, pulls = github.open_counts(info.full_name)
        # 他のリポジトリにもつながっている情報は、そちらで使っているので閉じない
        boards = [b for b in github.boards_of(info.full_name) if set(b.repositories) <= {info.full_name}]
        primary = found[0].root if found else None
        result = ModuleDeleted(info.full_name, info.web_url, issues, pulls, bool(boards), primary,
                               clones=tuple(c.root for c in found), done=not dry_run)
        if dry_run:
            return result
        for board in boards:   # 戻したときに探せるよう、どのリポジトリのものかを説明に書いてから閉じる
            github.describe_board(None, board.id, _board_description(info.full_name))
        github.delete_repository(info.full_name)
        for board in boards:
            github.close_board(board.id, closed=True)
        removed = []
        if remove_clone:   # 深い場所から（元のcloneの中に作業空間専用のcloneを作っていても消せるように）
            for c in sorted(found, key=lambda c: len(c.root.parts), reverse=True):
                try:
                    remove_tree(c.root)
                except OSError:
                    # 他のプログラム（エディター等）が使っている。GitHubの分は済んでいるので、残したことを知らせる。
                    # 中身は消せて空のフォルダーだけが残った（端末がその中にいる等）なら、消したものとして扱う
                    if not _empty_directory(c.root):
                        continue
                removed.append(c.root)
                _clones.forget(c.root)
        return replace(result, clone_removed=primary in removed, removed=tuple(removed))

    @classmethod
    def _recorded_clones(cls, full_name: str, github: _github.GitHub) -> list["Module"]:
        """このPCに記録した、full_name のclone（今あるもの）。"""
        found = []
        for entry in _clones.entries():
            if not entry.exists:
                continue
            if entry.repository is not None:
                if entry.repository.casefold() != full_name.casefold():
                    continue
            else:   # GitHubのものでない URL（ミラー等）は、GitHubに名前を聞く
                try:
                    if github.repository_name(entry.path).casefold() != full_name.casefold():
                        continue
                except WorkError:
                    continue
            try:
                found.append(cls(entry.path, _config.load(entry.path / _config.FILE_NAME), github=github))
            except EcoBuildError:
                continue
        return found

    @staticmethod
    def _check_nothing_unpushed_in(modules: list["Module"]) -> None:
        """どのcloneにも、手元にだけあるものがないことを確かめる（すべて見てから、まとめて知らせる）。"""
        found = []
        for module in modules:
            try:
                module._check_nothing_unpushed()
            except EcoBuildError as error:
                found += [f"{module.root}：{item}" for item in error.details or ()]
        if found:
            raise EcoBuildError(ErrorCode.UNFINISHED_WORK, "手元のcloneに、GitHubにないものがあります。",
                                hint="必要なものを残してから実行するか、手元のcloneを消さずに実行してください"
                                     "（--remove-clone を付けない）。", details=found)

    @staticmethod
    def _module_repository(name: str, github: _github.GitHub) -> _github.RepositoryInfo:
        info = github.get_repository(name)
        if not github.repository_has_file(info.full_name, _config.FILE_NAME):
            raise EcoBuildError(ErrorCode.NOT_IN_MODULE,
                                f"{info.full_name} はECOBuildのモジュールではありません（{_config.FILE_NAME} がありません）。",
                                hint="ECOBuildで作ったモジュールだけを扱えます。")
        return info

    def _check_nothing_unpushed(self) -> None:
        """手元にだけあるもの（未コミットの変更・GitHubにないコミット・退避）がないことを確かめる。依存先のcloneも。"""
        from ecowork.git import Git
        found = []
        nested = (*self.root.glob("*/.git"), *self.root.glob("*/*/.git"))   # 依存先のclone（型が置く。deps/<名前> 等）
        roots = [self.root] + sorted(p.parent for p in nested)
        for root in roots:
            git = Git(root)
            label = "" if root == self.root else f"{root.relative_to(self.root).as_posix()}："
            if git.output("status", "--porcelain"):
                found.append(f"{label}未コミットの変更")
            commits = git.output("log", "--branches", "--not", "--remotes", "--format=%h %s")
            if commits:
                found.append(f"{label}GitHubにないコミット {len(commits.splitlines())} 件")
            if git.output("stash", "list"):
                found.append(f"{label}退避した変更（stash）")
        if found:
            raise EcoBuildError(ErrorCode.UNFINISHED_WORK, f"手元のclone {self.root} に、GitHubにないものがあります。",
                                hint="必要なものを残してから実行するか、手元のcloneを消さずに実行してください"
                                     "（--remove-clone を付けない）。", details=found)

    def cloned(self, dependencies: tuple[DependencyChange, ...]) -> ModuleCloned:
        return ModuleCloned(self.name, self.root, self.remote_url or "", self.project_names, dependencies)

    @property
    def remote_url(self) -> str | None:
        return self.repository.remote_url

    @property
    def project_names(self) -> tuple[str, ...]:
        """今あるProject（型が Project を持たない・読めなければ空）。"""
        try:
            return tuple(p.name for p in self.type.projects())
        except EcoBuildError:
            return ()

    def summary(self) -> ModuleCreated:
        return ModuleCreated(self.name, self.root, self.remote_url or "", self.project_names)

    # 作業の進め方（ecowork） ---------------------------------------------------

    def status(self, *, fetch: bool = False) -> ws.Status:
        return self.repository.status(fetch=fetch)

    def tasks(self, *, closed: bool = False, label: str | None = None, assignee: str | None = None,
              search: str | None = None, milestone: str | None = None, ready: bool = False,
              sort: str | None = None, sprint: str | None = None) -> list[ws.TaskSummary]:
        tasks = self.repository.tasks(closed=closed, label=label, assignee=assignee, search=search,
                                      milestone=milestone, ready=ready, sort=sort, sprint=sprint)
        paths = self._workspace_paths()
        return [replace(t, workspace_path=paths.get(t.number, t.workspace_path)) for t in tasks]

    # 計画と判断（ecotask） ------------------------------------------------------------

    def plan_task(self, number: int, **values) -> ws.TaskSummary:
        """priority・due・estimate・sprint（名前か current）・planned_start・planned_end・clear（消す役割）・
        stage（作業を始める前の段階：planned・todo）。"""
        return self.repository.plan_task(number, **values)

    def next_tasks(self, *, assignee: str | None = None, count: int | None = None) -> list:
        return self.repository.next_tasks(assignee=assignee, count=count)

    def deadlines(self, *, days: int = 3):
        return self.repository.deadlines(days=days)

    def sprints(self) -> list:
        return self.repository.sprints()

    def sprint_status(self, name: str = "current"):
        return self.repository.sprint_status(name)

    def workload(self) -> list:
        return self.repository.workload()

    def milestone_status(self) -> list:
        return self.repository.milestone_status()

    def start_task_without_workspace(self, number: int, *, ignore_blocked: bool = False) -> ws.Task:
        return self.repository.start_task_without_workspace(number, ignore_blocked=ignore_blocked)

    def milestones(self, *, closed: bool = False) -> list[_github.MilestoneInfo]:
        return self.repository.milestones(closed=closed)

    def create_milestone(self, title: str, *, due: str | None = None, description: str = "") -> _github.MilestoneInfo:
        return self.repository.create_milestone(title, due=due, description=description)

    def edit_milestone(self, title: str, **changes) -> _github.MilestoneInfo:
        """new_title・due（"" で消す）・description・state（open／closed）（ecowork と同じ）。"""
        return self.repository.edit_milestone(title, **changes)

    def task_status(self, number: int | None = None) -> ws.TaskStatus:
        """作業空間の場所は、このPCの他のclone（作業空間専用のclone 等）も見る。"""
        status = self.repository.task_status(number)
        path = self._workspace_paths().get(status.number, status.workspace_path)
        task = None if status.task is None else replace(status.task, workspace_path=path)
        return replace(status, workspace_path=path, task=task)

    def edit_task(self, number: int, **changes) -> ws.Task:
        """title・body・add_labels・remove_labels・add_assignees・remove_assignees・plan・clear_plan 等
        （ecowork と同じ）。"""
        return self.repository.edit_task(number, **changes)

    def comment_task(self, number: int | None, body: str) -> ws.Task:
        return self.repository.comment_task(number, body)

    # PRの処理（ecowork と同じ） ---------------------------------------------------

    def pull_requests(self, *, closed: bool = False, review_requested: str | None = None) -> list[ws.PullRequest]:
        return self.repository.pull_requests(closed=closed, review_requested=review_requested)

    def pull_request_status(self, number: int | None = None) -> ws.PullRequestStatus:
        return self.repository.pull_request_status(number)

    def pull_request_diff(self, number: int | None = None) -> str:
        return self.repository.pull_request_diff(number)

    def comment_pull_request(self, number: int | None, body: str) -> ws.PullRequest:
        return self.repository.comment_pull_request(number, body)

    def review_pull_request(self, number: int, event: str, body: str = "") -> ws.PullRequest:
        return self.repository.review_pull_request(number, event, body)

    def edit_pull_request(self, number: int | None = None, **changes) -> ws.PullRequest:
        return self.repository.edit_pull_request(number, **changes)

    def close_pull_request(self, number: int | None = None) -> ws.PullRequest:
        return self.repository.close_pull_request(number)

    def reopen_pull_request(self, number: int) -> ws.PullRequest:
        return self.repository.reopen_pull_request(number)

    def set_pull_request_draft(self, number: int | None = None, *, draft: bool) -> ws.PullRequest:
        return self.repository.set_pull_request_draft(number, draft=draft)

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

    def start_task_in(self, number: int, directory: Path | str, *, base: str | None = None,
                      ignore_blocked: bool = False) -> "Module":
        """作業空間を専用のcloneで作り（I-007）、依存先と生成ファイルを用意する。

        準備（型の prepare）はclone先のモジュールでだけ行う（元のcloneの依存先・生成ファイルは変えない）。
        """
        opened: list[Module] = []

        def open_clone(root: Path) -> Repository:
            opened.append(Module.find(root, github=self.repository.github))
            return opened[0].repository

        self.repository.clone_workspace(number, directory, base=base, open=open_clone, ignore_blocked=ignore_blocked)
        return opened[0]

    def branches(self) -> list[ws.Branch]:
        return self.repository.branches()

    def branch(self, name: str) -> ws.Branch:
        return self.repository.branch(name)

    def create_branch(self, name: str, *, base: str | None = None) -> ws.Branch:
        return self.repository.create_branch(name, base=base)

    def create_task(self, title: str, *, body: str = "", labels: tuple[str, ...] = (),
                    assignees: tuple[str, ...] = (), parent: int | None = None, blocked_by: tuple[int, ...] = (),
                    milestone: str | None = None, plan: dict[str, str | None] | None = None) -> ws.Task:
        return self.repository.create_task(title, body=body, labels=labels, assignees=assignees, parent=parent,
                                           blocked_by=blocked_by, milestone=milestone, plan=plan)

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

    def remove_workspace(self, number: int | None = None) -> ws.RemoveResult:
        return self.repository.remove_workspace(number)

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
        self._reload()

    def stash(self) -> ws.StashResult:
        result = self.repository.stash()
        self._reload()
        return result

    def stash_pop(self) -> ws.StashResult:
        try:
            return self.repository.stash_pop()
        finally:
            self._reload()

    def stash_drop(self) -> ws.StashResult:
        return self.repository.stash_drop()

    def stashes(self) -> tuple[str, ...]:
        return self.repository.stashes()

    def restore(self, *paths: str, staged: bool = False) -> ws.RestoreResult:
        result = self.repository.restore(*paths, staged=staged)
        self._reload()
        return result

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

    def set_profile_project(self, name: str, project: str, values: dict | None) -> ProfileList:
        """ビルド設定 name の、Project ごとの上書きを変える（values が None なら外す）。"""
        self.require_workspace("ビルド設定の変更")
        if name not in self.config.profiles:
            raise EcoBuildError(ErrorCode.PROFILE_NOT_FOUND, f"ビルド設定 {name} はありません。",
                                hint=f"{COMMAND} profile add {name} で先に作ってください。")
        if values is not None and project not in {p.name for p in self.projects()}:
            raise EcoBuildError(ErrorCode.PROJECT_NOT_FOUND, f"Project {project} はありません。")
        current = self.config.profiles[name]
        projects = {k: v for k, v in current.projects.items() if k != project}
        if values:
            projects[project] = dict(values)
        profile = replace(current, projects=dict(sorted(projects.items())))
        self.type.validate_profile(profile)
        self._save_config(self.config.with_profiles({**self.config.profiles, name: profile}))
        return self.profiles()

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

    def projects(self) -> tuple[ProjectSummary, ...]:
        return self.type.projects()

    def add_project(self, name: str, kind: str, *, link: str | None = None, test: bool = True) -> FilesChanged:
        """kind：library（test なら組のテスト用 <名前>Test も）・app・test・bench（link のライブラリをリンク）。"""
        self.require_workspace("Projectの追加")
        if not _NAME.fullmatch(name):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"Project名 {name!r} は使えません。",
                                hint="英字で始まり、英数字と _ だけからなる名前にしてください。")
        return self.type.add_project(name, kind, link=link, test=test)

    def remove_project(self, name: str) -> FilesChanged:
        self.require_workspace("Projectの削除")
        return self.type.remove_project(name)

    def set_pch(self, project: str, *, enable: bool = True) -> FilesChanged:
        self.require_workspace("PCHの設定")
        return self.type.set_pch(project, enable=enable)

    # 保存する設定（型。管理ファイルが変わるので、変えるのは作業空間で） ------------------------------

    def module_settings(self) -> dict:
        return self.type.module_settings()

    def set_module_settings(self, **changes) -> dict:
        self.require_workspace("モジュールの設定")
        return self.type.set_module_settings(**changes)

    def add_template(self, name: str, source: Path | str) -> dict:
        self.require_workspace("テンプレートの登録")
        return self.type.add_template(name, Path(source))

    def remove_template(self, name: str) -> dict:
        self.require_workspace("テンプレートの削除")
        return self.type.remove_template(name)

    def project_details(self, name: str) -> dict:
        return self.type.project_details(name)

    def set_project(self, name: str, **changes) -> dict:
        self.require_workspace("Projectの設定")
        return self.type.set_project(name, **changes)

    def set_pch_headers(self, name: str, *, headers: tuple[str, ...] = (), system_headers: tuple[str, ...] = ()) -> dict:
        self.require_workspace("PCHの設定")
        return self.type.set_pch_headers(name, headers=headers, system_headers=system_headers)

    def move_project(self, name: str, destination: str) -> FilesChanged:
        self.require_workspace("Projectの移動")
        return self.type.move_project(name, destination)

    def link_project(self, name: str, library: str, *, as_type: str | None = None) -> dict:
        """同じモジュールのライブラリをリンクする（他のモジュールは link）。"""
        self.require_workspace("Projectのリンク")
        return self.type.link_project(name, library, as_type=as_type)

    def link_package(self, name: str, package: str, *, target: str, directory: str) -> dict:
        self.require_workspace("パッケージのリンク")
        return self.type.link_package(name, package, target=target, directory=directory)

    def link_cmake(self, name: str, directory: str, *, target: str) -> dict:
        self.require_workspace("CMakeのソースのリンク")
        return self.type.link_cmake(name, directory, target=target)

    def link_library_file(self, name: str, *, kind: str = "static", locations: dict[str, str] | None = None,
                          import_libraries: dict[str, str] | None = None,
                          include_directories: tuple[str, ...] = ()) -> dict:
        self.require_workspace("ビルド済みのライブラリのリンク")
        return self.type.link_library_file(name, kind=kind, locations=locations or {},
                                           import_libraries=import_libraries or {},
                                           include_directories=include_directories)

    def unlink_project(self, name: str, link: str) -> dict:
        self.require_workspace("Projectのリンクの解除")
        return self.type.unlink_project(name, link)

    def add_file(self, path: Path | str, *, test: bool = True, template: str | None = None) -> FilesChanged:
        """Projectにファイルを足す（テストを一緒に作るか等は型が決める）。template：使うファイルテンプレート。"""
        self.require_workspace("ファイルの追加")
        if template is None:
            return self.type.add_file(Path(path), test=test)
        return self.type.add_file(Path(path), test=test, template=template)

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

    def dependencies(self, *, fetch: bool = False) -> tuple[DependencyState, ...]:
        """依存先の状態。fetch：GitHubの側も確かめる（まだあるか・アーカイブ・名前の変更・新しい版）。"""
        states = self.type.dependencies()
        return tuple(self._remote_dependency(d) for d in states) if fetch else states

    def _remote_dependency(self, dependency: DependencyState) -> DependencyState:
        from ecowork.git import Git
        listed = Git(self.root).run("ls-remote", dependency.url, "HEAD", check=False)
        if not listed.ok:
            gone = re.search(r"not found|does not exist|does not appear to be a git repository", listed.output, re.I)
            return replace(dependency, remote="gone" if gone else "unknown")
        latest = listed.stdout.split()[0] if listed.stdout.strip() else None
        found = re.search(r"github\.com[:/]+([^/]+/[^/]+?)(?:\.git)?/?$", dependency.url)
        if found is None:
            return replace(dependency, remote="ok", latest=latest)
        try:
            info = self.repository.github.get_repository(found.group(1))
        except WorkError:
            return replace(dependency, remote="unknown", latest=latest)
        if info.full_name.casefold() != found.group(1).casefold():
            return replace(dependency, remote="moved", latest=latest, moved_to=info.full_name)
        return replace(dependency, remote="archived" if info.archived else "ok", latest=latest)

    def dependency_tree(self) -> DependencyTree:
        """依存関係の図（依存先の依存先も）。"""
        return self.type.dependency_tree()

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

    def write_ci(self, settings: _config.CiSettings | None = None, *, force: bool = False) -> CiInitResult:
        """GitHub Actions のワークフロー（中身は型が用意する）を、CIの設定（[ci]）から作る。

        settings を渡すと [ci] に保存してから作る。手で編集したワークフロー（作ったときの印と内容が合わない）は、
        force がなければ上書きしない。非公開の依存先は、CIの GITHUB_TOKEN では取得できない。その依存先を返す。
        """
        self.require_workspace("CIの設定の作成")
        path = self.root / _docs.CI_WORKFLOW
        if path.is_file() and not force and _docs.ci_edited(path.read_text(encoding="utf-8")):
            raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{_docs.CI_WORKFLOW} は手で編集されています。",
                                hint="上書きしてよければ --force を付けてください（編集した内容は失われます）。")
        new_config = self.config if settings is None else self.config.with_ci(settings)
        workflow = self.type.ci_workflow(new_config)
        if workflow is None:
            raise self.type.not_supported("CI")
        if new_config is not self.config:
            self._save_config(new_config)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_docs.stamp_ci(workflow), encoding="utf-8", newline="\n")
        private = []
        for dependency in self.type.dependencies():
            name = dependency.url.removesuffix(".git").split("github.com/")[-1]
            try:
                if self.repository.github.is_private(name):
                    private.append(dependency.name)
            except Exception:  # GitHub以外・見つからない等は案内しない
                continue
        return CiInitResult(_docs.CI_WORKFLOW, tuple(private))

    def ci_wait(self, pull_request: int | None = None, *, timeout: float = 1800) -> list:
        return self.repository.ci_wait(pull_request, timeout=timeout)

    def delete_secret(self, name: str) -> str:
        return self.repository.delete_secret(name)

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
        self._record_check(report.ok and build)
        if not report.ok:
            raise EcoBuildError(ErrorCode.CHECK_FAILED, "確認で問題が見つかりました：" +
                                "、".join(i.name for i in items if not i.ok),
                                hint=f"内容を直して、もう一度 {COMMAND} check を実行してください。",
                                details=[{"name": i.name, "ok": i.ok, "detail": i.detail} for i in items])
        return report

    def checked(self) -> bool:
        """今の版が、ビルド・テストを含む check を通ったままか（task submit --check で繰り返さないため）。"""
        key = self._check_key()
        record = self._check_record()
        return key is not None and record.is_file() and record.read_text(encoding="utf-8").strip() == key

    # 内部 -----------------------------------------------------------------

    def _check_record(self) -> Path:
        return self.root / self.repository.git.output("rev-parse", "--git-path", "ecobuild-checked")

    def _check_key(self) -> str | None:
        """check の結果を使い回せる状態：コミットの版と、このPCで選んだビルド設定。変更が残っていれば使い回さない。"""
        git = self.repository.git
        tree = git.working_tree()
        if tree.staged or tree.unstaged or tree.untracked or tree.conflicted:
            return None
        return f"{git.rev_parse('HEAD')} {_config.load_local(self.root).get('profile') or '-'}"

    def _record_check(self, passed: bool) -> None:
        record = self._check_record()
        key = self._check_key() if passed else None
        if key is None:
            record.unlink(missing_ok=True)
        else:
            record.write_text(key + "\n", encoding="utf-8")


    def _save_config(self, module_config: _config.ModuleConfig) -> None:
        _config.save(module_config, self.root / _config.FILE_NAME)
        self.config = module_config

    @staticmethod
    def _sync_result(result: ws.SyncResult) -> SyncResult:
        dependencies, regenerated = result.extra if result.extra is not None else ((), False)
        return SyncResult(result.branch, result.merged, dependencies, regenerated)

    def _after_sync(self) -> PrepareResult:
        """Git操作（切り替え・取り込み・確認の開始と終了・取り消し）の後：設定を読み直し、型に手元をそろえさせる。"""
        self._reload()
        return PrepareResult(*self.type.prepare())

    def _reload(self) -> None:
        """ecobuild.toml が変わっていれば、設定・型・作成元の既定を読み直す（同じ Module を使い続けるため）。

        読めない（衝突の印が残っている等）ときは前の設定のまま（取り込みを終えた後にもう一度読む）。
        """
        try:
            new_config = _config.load(self.root / _config.FILE_NAME)
        except EcoBuildError:
            return
        if new_config == self.config:
            return
        if new_config.type != self.config.type:
            self.type = _module_type.load(new_config.type)(self)
        self.config = new_config
        self.repository.default_base = new_config.default_base

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


def _module_type_of(text: str | None) -> str:
    """ecobuild.toml の中身から、モジュールの型（読めなければ空）。"""
    try:
        value = tomllib.loads(text or "").get("module", {}).get("type")
    except tomllib.TOMLDecodeError:
        return ""
    return value if isinstance(value, str) else ""


def _with_gap(text: str) -> str:
    return "\n" + text if text else ""


def _github_state(github: _github.GitHub, name: str) -> tuple[str, str | None]:
    """GitHubのリポジトリの今：ok・archived・moved（名前が変わった。今の名前も返す）・gone（ない）・unknown。"""
    try:
        info = github.get_repository(name)
    except WorkError as error:
        return ("gone" if error.code == ErrorCode.REPOSITORY_NOT_FOUND else "unknown"), None
    if info.full_name.casefold() != name.casefold():
        return "moved", info.full_name
    return ("archived" if info.archived else "ok"), None


def _empty_directory(path: Path) -> bool:
    try:
        return not any(path.iterdir())
    except OSError:
        return False
