"""モジュール：ECOBuildの管理単位（GitHubリポジトリ）。

作業の進め方（タスクブランチ・ブランチ・提出・最新化・タスク・CI 等）は ecowork.Repository が受け持ち、使う側は
module.repository を直接使う。言語ごとの処理（ビルド・Project・ファイル・依存先・生成ファイル）は、モジュールの型
（module_type）が受け持つ。

Module が持つのは、モジュールそのもの（作成・clone・削除・ecobuild.toml）と型の操作、そして作業の流れのうち
型・管理するファイル・確認（check）が関わる操作だけ（commit・submit・finish・sync 等）。作業の流れの途中で型に
手元をそろえさせる処理は、フック（_TypeHooks）で ecowork に差し込むので、module.repository を直接使っても抜けない。
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import json

import re
from collections.abc import Callable
import tomllib
from dataclasses import fields, replace
from pathlib import Path

from ecowork import Hooks, Repository, WorkError
from ecowork import github as _github
from ecowork import model as wm
from ecowork.git import CLONE_CONFIG as _CLONE_CONFIG, Git as _Git, WORKTREE_LOCK_REASON as _LOCK_REASON

from . import _docs
from . import ci_review as _ci_review
from . import config as _config
from . import locks as _locks
from . import module_type as _module_type
from . import tracking as _tracking
from . import workspaces as _workspaces
from .module_type import Builds, HasDependencies, HasFiles, HasProjects, Registry
from .errors import EcoBuildError, ErrorCode, operation
from .fsutil import remove_tree
from .results import (AgentGuide, BuildResult, CheckItem, CheckReport, CiInitResult, CiState, DependencyChange, DependencyState,
                      DependencyTree, FilesChanged, LinkResult, ModuleAdopted, ModuleArchived, ModuleCloned, ModuleCreated,
                      ModuleDeleted, ModuleEntry, ModuleInfo, ModuleStatus, ModuleUpgraded, PrepareResult, ProfileList,
                      ProjectSummary, RunResult, SyncResult, TestResult, WorkspaceClosed, WorkspaceList)

_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_WORKSPACE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")
_UNPUSHED_HINT = ("必要なものを GitHub へ送るか（コミット・push・退避の取り出し等）、捨ててよければ --discard-local を付けて"
                  "実行してください（それらは失われます）。")

# .ecobuild/.gitignore：このPC用の設定とログ（CLI）はコミットしない
GITIGNORE = """\
ecobuild.local.toml
logs/
"""

# .ecobuild/.gitattributes：ECOBuild・型（CppBuild 等）は .ecobuild/ の中のファイルをLFで書く。gitの改行変換
# （Windowsのcore.autocrlf=true等）でCRLFにされると、作り直すたびに「変更あり」になるため、LFに固定する。
GITATTRIBUTES = """\
* text eol=lf
"""


UPGRADE_MESSAGE = "ECOBuild の更新"   # module upgrade のコミット（ECOBuild 自身が作る）
ADOPT_MESSAGE = "ECOBuild のモジュールにする"   # module adopt のコミット

# モジュールの仕様の版ごとの移行（版 → その版のモジュールを次の版にする処理）。ECOBuild が作るファイルの中身を
# 変えただけなら要らない（Module.upgrade が毎回作り直す）。置き場所を変えた・設定の書き方を変えた等のときに足す。
_MIGRATIONS: dict[int, Callable[["Module"], None]] = {}


def _with_lines(current: str, wanted: str) -> str:
    """current に、wanted の行（空行・# の行を除く）のうち足りないものを足す（.gitignore 等。足した行は残す）。

    全体の決まり（パターンが * だけの行。.gitattributes の「* text=auto eol=lf」等）は先頭に、ほかは末尾に足す：
    .gitattributes は後の行が勝つので、末尾に足すと既にある個別の決まり（*.ps1 eol=crlf 等）を上書きしてしまう。
    """
    have = {line.strip() for line in current.splitlines()}
    missing = [line for line in wanted.splitlines() if line.strip() and not line.startswith("#") and line.strip() not in have]
    if not current:
        return wanted
    if not missing:
        return current
    first = [line for line in missing if line.split()[0] == "*"]
    last = [line for line in missing if line.split()[0] != "*"]
    text = "".join(line + "\n" for line in first) + current
    return text + ("" if text.endswith("\n") else "\n") + "".join(line + "\n" for line in last) if last else text


def _locked_hint(command: str) -> str:
    """ロック中で止めたときのヒント（外し方。--force は案内しない）。"""
    return ("ロックの原因を終わらせてから、もう一度実行してください（エージェントを止める・コンテナを止める・"
            f"実行中のコマンドが終わるのを待つ。手動のロックなら {operation(command, 'workspace unlock')} で外せます）。")


class _TypeHooks(Hooks):
    """作業の流れの途中で、モジュールの型に手元（依存先・生成ファイル）をそろえさせる。作業空間を消すのは Module。

    1つの Module（その作業空間）に結び付く。別の作業空間の Repository には渡さない（start_task_in を参照）。
    """

    def __init__(self, module: "Module"):
        self._module = module

    def after_sync(self, repository: Repository) -> PrepareResult:
        return self._module._after_sync()

    def prepare_workspace(self, repository: Repository) -> None:
        # 作った作業空間・その場で切り替えた先の記録に、手元をそろえる（作業版・変更のある依存先は型が触らない）。
        self._module._after_sync()

    def before_submit(self, repository: Repository) -> None:
        self._module._check_generated_files()

    def unusable(self, repository: Repository, refs: list[str]) -> dict[str, str]:
        # モジュールでないブランチ（ecobuild.toml がない。adopt する前・GitHub の既定のブランチ等）には移らない：
        # 移るとこの clone がモジュールでなくなる。1回の git で全部を調べる。
        if not refs:
            return {}
        lines = repository.git.run("cat-file", "--batch-check", input="".join(
            f"{ref}:{_config.FILE_NAME}\n" for ref in refs)).stdout.splitlines()
        return {ref: "ECOBuild のモジュールではありません" for ref, line in zip(refs, lines) if line.endswith(" missing")}

    def switch_locks(self, repository: Repository) -> list[str]:
        return [r.text for r in _locks.status(repository.root).reasons]

    def branch_locks(self, repository: Repository, branch: str) -> list[str]:
        # そのタスクブランチを取り出している、ほかの作業ツリー（作業空間・元の clone。git worktree list）と、同じリポジトリの
        # 前の版の作業空間（独立した clone）のうち、ロック中のもの（場所を添える）
        held = repository.git.checked_out_branches().get(branch)
        here = [held] if held is not None and not _workspaces.same(held, repository.root) else []
        mine = _workspaces.identity(repository.remote_url)
        for path in _workspaces.legacy() if mine is not None else ():
            if (_workspaces.same(path, repository.root) or any(_workspaces.same(path, p) for p in here)
                    or not (path / _config.FILE_NAME).is_file()):
                continue
            try:
                git = _Git(path)
                if git.current_branch() == branch and _workspaces.identity(git.get_config("remote.origin.url")) == mine:
                    here.append(path)
            except Exception:   # gitで読めない（壊れたclone 等）
                continue
        return [f"{path}：{reason.text}" for path, lock in zip(here, _locks.status_of(here)) for reason in lock.reasons]

    def remove_workspace(self, repository: Repository, path: Path, *, discard: bool) -> bool:
        # タスクブランチを消す前に、それを取り出している作業空間を消す（ecowork が、失われるコミット・コミットしていない
        # 変更を確かめた後）。管理するファイルに当たる新しいファイルは、discard でなければ残す（消えてしまうため）。
        # ECOBuild の置き場所（.ecobuild/ の中）の作業空間でなければ（人が git worktree で作ったもの等）触らない：ブランチは残る
        if not _workspaces.is_managed(path):
            raise EcoBuildError(ErrorCode.BRANCH_CHECKED_OUT,
                                f"ECOBuild が作った作業空間ではない作業ツリー {path} が取り出しています（消しません）",
                                hint=f"git worktree remove \"{path}\" で外してから、{self._module.op('task prune')} で"
                                     "片付けてください。")
        if not discard:
            other = self._module._open_workspace(Path(path))
            pending = [p for p in other.repository.git.working_tree().untracked if other.is_tracked(p)]
            if pending:
                raise EcoBuildError(ErrorCode.DIRTY_WORKING_TREE, f"作業空間 {path} に、コミットしていない新しいファイルがあります。",
                                    hint=f"{self._module.op('task commit')} で記録するか、要らなければ消してから、もう一度実行してください。",
                                    details=pending)
        type(self._module).close_workspace(path, discard_local=True, github=repository.github)
        return True


class Module:
    """1つのモジュール（GitHubのリポジトリ）。

    使える型は registry（Registry）。クラスの属性を子クラスで決めるか、作るときに渡す（本体の既定は空）。
    このモジュールが開く別の Module（task start の作業空間等）も、同じ registry を使う。
    """

    registry: Registry = Registry()
    command: str = ""     # ヒントに書くプログラム名（CLI は ecobuild）。空なら操作名だけ（errors.operation）
    reviewed: wm.ReviewResult | None = None   # 確認用の作業空間として開いた（review）ときの、取り出した結果

    def __init__(self, root: Path, module_config: _config.ModuleConfig, *, github: _github.GitHub | None = None,
                 registry: Registry | None = None):
        self.root = Path(root)
        self.config = module_config
        self.registry = registry or type(self).registry
        self.repository = Repository(self.root, github=github, default_base=module_config.default_base,
                                     command=self.command, hooks=_TypeHooks(self),
                                     legacy_board=module_config.legacy_board,
                                     require_approval=_require_approval(module_config))
        self.repository.include_new = self.is_tracked   # 管理しない新しいファイルは、タスクブランチの切り替え等を止めない
        self.type: _module_type.ModuleType = self.registry.load(module_config.type, command=self.command)(self)

    @property
    def name(self) -> str:
        return self.config.name

    def op(self, name: str) -> str:
        """ヒントに書く操作（「ecobuild task commit」等）。型もヒントにはこれを使う。"""
        return operation(self.command, name)

    @classmethod
    def find(cls, path: Path | str = ".", *, github: _github.GitHub | None = None,
             registry: Registry | None = None) -> "Module":
        """pathから上へecobuild.tomlを探し、最も近いモジュールを返す（I-027）。"""
        root = _config.find_root(Path(path), command=cls.command)
        return cls(root, _config.load(root / _config.FILE_NAME), github=github, registry=registry)

    def _open_workspace(self, root: Path) -> "Module":
        """作業空間 root そのものを、このモジュールとして開く。上へはたどらない：作業空間は元の clone の中（.ecobuild/w）に
        作るので、たどると外のモジュール（元の clone）を開いて、そのブランチを変える。"""
        if not (Path(root) / _config.FILE_NAME).is_file():
            raise EcoBuildError(ErrorCode.NOT_IN_MODULE,
                                f"作業空間 {root} はECOBuildのモジュールではありません（{_config.FILE_NAME} がありません）。",
                                hint=f"取り出した作成元のブランチにモジュールがありません。作成元には、モジュールのブランチ"
                                     f"（{self.op('branch list')}）を指定してください。")
        return type(self)(Path(root), _config.load(Path(root) / _config.FILE_NAME),
                          github=self.repository.github, registry=self.registry)

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
        type: str | None = None,
        github: _github.GitHub | None = None,
        registry: Registry | None = None,
        progress: Callable[[str], None] | None = None,
        test: bool = True,
    ) -> "Module":
        """GitHubリポジトリを作り、型が用意する中身と共に初回コミットをpushする。タスク管理も準備する
        （できなければ知らせ、タスクを初めて記録するときにもう一度行う）。

        kind：最初に作るもの（型の new_kinds。C++：app＝実行ファイル〔既定〕・library＝ライブラリとテスト用・
        none＝作らない）。モジュールはリンクのための単位ではなく、中身は後から project add で足す。
        project：最初に作るProjectの名前（省略時はモジュール名。ライブラリならテスト用は <名前>Test）。
        test：ライブラリのテスト（C++ ならテスト用のProject）も作る（既定）。
        type：モジュールの型（省略時は registry の既定の型）。githubは試験でGitHubへの接続を差し替えるためのもの。
        progress：経過（今している作業）を知らせる口。
        """
        if not _NAME.fullmatch(name):
            raise EcoBuildError(
                ErrorCode.INVALID_CONFIG,
                f"モジュール名 {name!r} は使えません。",
                hint="英字で始まり、英数字と _ だけからなる名前にしてください。",
            )
        registry = registry or cls.registry
        type_class = registry.load(type, command=cls.command)
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
        type_class.check_new(name, kind or None, project or None, test=test)
        module_config = type_class.new_config(name)

        def populate(root: Path) -> None:
            _config.save(module_config, root / _config.FILE_NAME)
            (root / _config.DIRECTORY / ".gitignore").write_text(GITIGNORE, encoding="utf-8", newline="\n")
            (root / _config.DIRECTORY / ".gitattributes").write_text(GITATTRIBUTES, encoding="utf-8", newline="\n")
            if type_class.gitignore():
                (root / ".gitignore").write_text(type_class.gitignore(), encoding="utf-8", newline="\n")
            if type_class.gitattributes():
                (root / ".gitattributes").write_text(type_class.gitattributes(), encoding="utf-8", newline="\n")
            (root / "README.md").write_text(_docs.readme(module_config, type_class, description), encoding="utf-8", newline="\n")
            (root / _docs.ECOBUILD_README).write_text(_docs.ecobuild_readme(module_config, type_class), encoding="utf-8",
                                                      newline="\n")
            for path, text in cls.environment_files(type_class).items():
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_text(text, encoding="utf-8", newline="\n")
            (progress or _quiet)(_POPULATING.get(kind or type_class.default_new_kind or "", "モジュールの中身を用意中…"))
            type_class.populate(root, module_config, kind or None, project or None, test=test)

        repository = Repository.create(
            name, directory=directory, description=description, private=not public, owner=owner,
            populate=populate, message="ECOBuildでモジュールを作成", github=github,
            default_base=module_config.default_base, command=cls.command, progress=progress,
        )
        module = cls(repository.root, module_config, github=repository.github, registry=registry)
        try:
            (progress or _quiet)("タスク管理を準備中…")
            module.repository.prepare_tasks()
        except WorkError as error:
            module.repository.notices.append(f"タスク管理の準備ができませんでした（{error.message}）。"
                                             "タスクを初めて記録するときに、もう一度行います。")
        return module

    @classmethod
    def environment_files(cls, type_class: type[_module_type.ModuleType]) -> dict[str, str]:
        """拡張がモジュールに置くファイル（モジュールのルートからの場所 → ひな型。例：コンテナの環境の Dockerfile）。
        module new で置き、module upgrade ではなければ置く（あればモジュールのもの。変えない）。本体は置かない：
        Module に重ねる拡張が、super() に足して返す。"""
        return {}

    @classmethod
    def clone(
        cls, name: str, *, directory: Path | str = ".", github: _github.GitHub | None = None,
        registry: Registry | None = None, progress: Callable[[str], None] | None = None,
    ) -> tuple["Module", tuple[DependencyChange, ...]]:
        """GitHubにあるモジュールをcloneし、依存先と生成ファイルを用意する（sync と同じ）。

        name は「名前」（ログイン中のユーザーのもの）か「所有者/名前」。progress：経過を知らせる口。
        """
        repository = Repository.clone(name, directory=directory, github=github, command=cls.command, progress=progress)
        if not (repository.root / _config.FILE_NAME).is_file():
            remove_tree(repository.root)  # 今cloneしたもの
            raise EcoBuildError(
                ErrorCode.NOT_IN_MODULE,
                f"{name} はECOBuildのモジュールではありません（{_config.FILE_NAME} がありません）。",
                hint=f"ECOBuildで作ったリポジトリ（{operation(cls.command, 'module new')}）を指定してください。ほかのリポジトリは、"
                     f"clone してから {operation(cls.command, 'module adopt')} でモジュールにできます。",
            )
        module = cls.find(repository.root, github=repository.github, registry=registry)
        (progress or _quiet)("依存先と生成ファイルを用意中…")
        dependencies, _ = module._after_sync()
        return module, dependencies

    @classmethod
    def adopt(
        cls, path: Path | str = ".", *, type: str | None = None, dry_run: bool = False,
        github: _github.GitHub | None = None, registry: Registry | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> tuple["Module", ModuleAdopted]:
        """既にある GitHub のリポジトリ（path を含む clone）を、ECOBuild のモジュールにする。

        今のブランチに .ecobuild/（ecobuild.toml 等）・拡張が置くファイル・型が要るもの（adopt）を置き、.gitignore・
        .gitattributes には足りない行を足して、「ECOBuild のモジュールにする」として1回コミットし、GitHub へ push する。
        今のブランチがタスクブランチの作成元（default_base）になる。名前は GitHub のリポジトリ名。README・AGENTS.md 等、
        元からあるファイルは変えない。できるのはリポジトリの管理者（admin）だけ（個人のリポジトリなら持ち主だけ。GitHub には
        リポジトリを作った人の記録がないので、組織のリポジトリでは管理者を作った人とみなす）。
        未コミットの変更・GitHub に遅れている・GitHub にないブランチのときは止める。
        type：モジュールの型（省略時は registry の既定の型）。dry_run：置くファイルを返すだけ（型が置くものは含まない）。
        """
        start = Path(path)
        try:
            root = Path(Repository(start).git.output("rev-parse", "--show-toplevel").strip())
        except WorkError:
            raise EcoBuildError(ErrorCode.REPOSITORY_NOT_FOUND, f"{start} は git のリポジトリ（clone）の中ではありません。",
                                hint=f"GitHub のリポジトリを clone して、その中で実行してください（新しく作るなら "
                                     f"{operation(cls.command, 'module new')}）。") from None
        try:
            found = _config.find_root(start, command=cls.command)
        except EcoBuildError:
            found = None
        if found is not None:
            raise EcoBuildError(ErrorCode.ALREADY_EXISTS,
                                f"{found} は既に ECOBuild のモジュールです。" if _workspaces.same(found, root)
                                else f"{root} は ECOBuild のモジュール {found} の中にあります（依存先の clone 等）。",
                                hint=f"今の仕様に合わせるなら {operation(cls.command, 'module upgrade')}。")
        registry = registry or cls.registry
        type_class = registry.load(type, command=cls.command)
        repository = Repository(root, github=github, command=cls.command)
        repository.require_admin("ECOBuild のモジュールにすること")   # 個人のリポジトリなら持ち主だけ（ほかの人のものはできない）
        repository.check_own_commit("モジュールにすること")
        branch = repository.git.current_branch() or ""
        if not repository.git.has_remote_branch(branch):
            raise EcoBuildError(ErrorCode.BRANCH_NOT_FOUND, f"GitHub に {branch} がありません。",
                                hint="GitHub にあるブランチ（main 等）に切り替えてから実行してください（印はそのブランチに置きます）。")
        name = repository.github.repository_name(root).partition("/")[2]
        if not _NAME.fullmatch(name):
            raise EcoBuildError(ErrorCode.INVALID_CONFIG, f"リポジトリ名 {name!r} はモジュール名に使えません。",
                                hint="GitHub でリポジトリ名を、英字で始まり英数字と _ だけからなる名前に変えてから実行してください。")
        module_config = replace(type_class.new_config(name), default_base=branch)
        module = cls(root, module_config, github=repository.github, registry=registry)
        planned, _ = module._ecobuild_files(rewrite=False)
        paths = tuple(sorted({_config.FILE_NAME, *planned}))
        if dry_run:
            return module, ModuleAdopted(name, root, type_class.name, branch, paths, dry_run=True)
        before = set(module._changed_paths())
        originals = {p: (root / p).read_bytes() if (root / p).is_file() else None for p in paths}
        created = not (root / _config.DIRECTORY).exists()
        try:
            _config.save(module_config, root / _config.FILE_NAME)
            for item, text in planned.items():
                (root / item).parent.mkdir(parents=True, exist_ok=True)
                (root / item).write_text(text, encoding="utf-8", newline="\n")
            (progress or _quiet)(f"型 {type_class.name} の用意中…")
            type_class.adopt(root, module_config)
            module.type.refresh()
        except BaseException:   # 置いたものを片付けて、元のリポジトリに戻す
            for item, data in originals.items():
                if data is None:
                    (root / item).unlink(missing_ok=True)
                else:
                    (root / item).write_bytes(data)
            if created:
                remove_tree(root / _config.DIRECTORY)
            raise
        changed = tuple(sorted((set(module._changed_paths()) - before) | set(paths)))
        commit, branch, pushed = module.repository.commit_own(changed, ADOPT_MESSAGE)
        try:
            (progress or _quiet)("タスク管理を準備中…")
            module.repository.prepare_tasks()
        except WorkError as error:
            module.repository.notices.append(f"タスク管理の準備ができませんでした（{error.message}）。"
                                             "タスクを初めて記録するときに、もう一度行います。")
        return module, ModuleAdopted(name, root, type_class.name, branch, changed, commit=commit, pushed=pushed)

    @staticmethod
    def modules(owner: str | None = None, *, archived: bool | None = False,
                github: _github.GitHub | None = None) -> tuple[ModuleEntry, ...]:
        """GitHubにある、所有者（既定はログイン中のユーザー）のECOBuildのモジュール（ecobuild.toml があるリポジトリ）。
        archived：False＝アーカイブしていないもの、True＝アーカイブしたものだけ、None＝両方。新しく更新した順。"""
        github = github or _github.default()
        return tuple(ModuleEntry(r.full_name, r.url, _module_type_of(r.module_file), r.description, r.private,
                                 r.archived, r.updated)
                     for r in github.owner_repositories(owner, _config.FILE_NAME)
                     if r.module_file is not None and (archived is None or r.archived == archived))

    @staticmethod
    def workspaces(*, fetch: bool = False, github: _github.GitHub | None = None) -> WorkspaceList:
        """このPCにあるモジュール（記録した元の clone と、その中の作業空間）と、前の版の作業空間。fetch：GitHubの側も
        確かめる（まだあるか・アーカイブ・名前の変更）。GitHubのものでない origin は確かめない。"""
        listed = _workspaces.listing()
        if not fetch:
            return listed
        github = github or _github.default()
        states: dict[str, tuple[str, str | None]] = {}
        for entry in (*listed.modules, *listed.legacy):
            if entry.repository and entry.repository.casefold() not in states:
                states[entry.repository.casefold()] = _github_state(github, entry.repository)

        def checked(entry):
            if not entry.repository:
                return entry
            remote, moved_to = states[entry.repository.casefold()]
            return replace(entry, remote=remote, moved_to=moved_to)
        return WorkspaceList(tuple(map(checked, listed.modules)), tuple(map(checked, listed.legacy)))

    @property
    def workspace_root(self) -> Path:
        """元の clone（作業空間を置くモジュール）。作業空間（git worktree）の中ならその元、前からある独立した clone・
        依存先の clone ならそれ自身。"""
        return _workspaces.original_of(self.root)

    def workspace_place(self, name: str) -> Path:
        """作業空間の場所：<元の clone>/.ecobuild/w/<name>。name は英数字で始まる、英数字・_・- の32文字まで（外へ出る
        名前・パスの区切りは受け付けない）。"""
        if not _WORKSPACE_NAME.fullmatch(name or ""):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"作業空間の名前 {name!r} は使えません。",
                                hint="英数字で始まる、英数字・_・- の32文字までの名前にしてください（タスクの番号等）。")
        return _workspaces.area(self.workspace_root) / name

    def task_workspaces(self) -> dict[int, Path]:
        """このモジュールのタスクブランチを取り出している場所（タスクの番号 → 場所）：元の clone の git worktree list
        （元の clone・作業空間）と、同じリポジトリの前の版の作業空間（独立した clone）。"""
        found: dict[int, Path] = {}
        mine = _workspaces.identity(self.remote_url)
        for path in _workspaces.legacy() if mine is not None else ():
            if not (path / _config.FILE_NAME).is_file():
                continue
            try:
                git = _Git(path)
                number = wm.task_number(git.current_branch() or "")
                if number is not None and _workspaces.identity(git.get_config("remote.origin.url")) == mine:
                    found[number] = path
            except Exception:   # gitで読めない（壊れたclone 等）
                continue
        for worktree in self.repository.git.worktrees():
            number = wm.task_number(worktree.branch) if worktree.branch and not worktree.prunable else None
            if number is not None:
                found[number] = worktree.path
        return found

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
                          self.config.default_base, self.project_names, dependencies,
                          tuple(_workspaces.task_workspaces(self.workspace_root)),
                          self.config.format, _config.FORMAT)

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
        cls, name: str, *, clone: "Module | None" = None, remove_workspaces: bool = False, discard_local: bool = False,
        dry_run: bool = False, github: _github.GitHub | None = None,
    ) -> ModuleDeleted:
        """アーカイブしたモジュール（リポジトリ）を削除する。GitHubの機能で、90日以内なら元に戻せる。

        タスク管理の情報は消さずに閉じる（リポジトリを戻すと、ECOBuildが開き直して使う）。
        手元の作業空間：clone（今いる等。このモジュールのもの）と、このPCに記録した、このモジュールの作業空間すべて。
        remove_workspaces なら一緒に削除し、記録から外す（どれか1つにでもGitHubにない変更・コミット・退避があれば、
        何もせずに断る。discard_local なら、それも捨てて削除する）。
        作業空間は、GitHubで何かする前に脇へ移す（他のプログラムが使っていれば動かせないので、その時点で何もせずに断る。
        GitHubだけ消えて、手元が途中まで消えた作業空間が残ることがないように）。dry_run：確かめて、何をするかを返すだけ。
        """
        github = github or _github.default()
        info = cls._module_repository(name, github)
        if not info.archived:
            raise EcoBuildError(ErrorCode.NOT_ARCHIVED, f"{info.full_name} はアーカイブしていません。",
                                hint=f"削除する前に、{operation(cls.command, 'module archive')} {info.full_name} でアーカイブしてください"
                                     "（読み取り専用にし、使っていないことを確かめる段階です）。")
        if clone is not None and github.repository_name(clone.root) != info.full_name:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{clone.root} は {info.full_name} のcloneではありません。")
        found = ([clone] if clone is not None else []) + [
            c for c in cls._recorded_workspaces(info.full_name, github)
            if clone is None or not _workspaces.same(c.root, clone.root)]
        if remove_workspaces and not discard_local:
            cls._check_nothing_unpushed_in(found)
        issues, pulls = github.open_counts(info.full_name)
        # 他のリポジトリにもつながっている情報は、そちらで使っているので閉じない
        boards = [b for b in github.boards_of(info.full_name) if set(b.repositories) <= {info.full_name}]
        primary = found[0].root if found else None
        result = ModuleDeleted(info.full_name, info.web_url, issues, pulls, bool(boards), primary,
                               workspaces=tuple(c.root for c in found), done=not dry_run)
        if dry_run:
            return result
        # 一番外側の作業空間だけを移す（作業空間の中に別の作業空間を作っていれば、一緒に移る）
        outer = [c.root for c in found if not any(o.root != c.root and o.root in c.root.parents for o in found)]
        aside = _set_aside(outer) if remove_workspaces else []
        try:
            for board in boards:   # 戻したときに探せるよう、どのリポジトリのものかを説明に書いてから閉じる
                github.describe_board(None, board.id, _github.board_description(info.full_name))
            github.delete_repository(info.full_name)
        except BaseException:
            _put_back(aside)
            raise
        for board in boards:
            github.close_board(board.id, closed=True)
        removed = []
        for original, moved in aside:
            try:
                remove_tree(moved)
            except OSError:
                # 移した後で他のプログラムが使い始めた（まれ）。中身が残っていれば、元の場所に戻して知らせる
                if not _empty_directory(moved):
                    _put_back([(original, moved)])
                    continue
                with contextlib.suppress(OSError):
                    moved.rmdir()
            removed += [c.root for c in found if c.root == original or original in c.root.parents]
        for path in removed:
            _workspaces.forget(path)
        return replace(result, workspace_removed=primary in removed, removed=tuple(removed))

    @classmethod
    def close_workspace(cls, path: Path | str, *, discard_local: bool = False, dry_run: bool = False,
                        github: _github.GitHub | None = None) -> WorkspaceClosed:
        """作業空間を閉じる：場所ごと消す。GitHubのリポジトリ・ブランチ・タスクには触らない。

        閉じられるのは、作業空間（git worktree。.ecobuild/w/ の中）と、前の版の作業空間（独立した clone。記録からも外す）。
        元の clone は閉じられない（モジュールを手元から消すのは module delete --remove-workspaces）。
        手元にだけあるもの（未コミットの変更・新しいファイル・GitHubにないコミット・退避。依存先のcloneも）があれば断る
        （discard_local なら、それも捨てる）。除外したファイル（ビルドの出力・このPC用の設定・ログ）は一緒に消える。
        使用中（ロック中・before_close_workspace が理由を返す）なら断る。
        他のプログラム（端末・エディター等）が使っていてフォルダーを動かせなければ、前の版の作業空間は消せるものだけを消し、
        残ったものを返す（GitHubにないものがないことは確かめてあるので、作業は失われない）。作業空間（git worktree）は
        記録が残るので消さずに断る。
        """
        root = _workspaces.module_root(Path(path))
        linked = _Git(root).is_linked_worktree()
        if not linked and not _workspaces.is_legacy(root):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{root} は元の clone なので閉じられません（作業空間はその中に作ります）。",
                                hint=f"閉じるのは作業空間（{_workspaces.AREA}/<名前>）です（{operation(cls.command, 'workspace list')}）。"
                                     f"このPCの一覧から外すだけなら {operation(cls.command, 'workspace forget')}。")
        if linked and not _workspaces.is_managed(root):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                                f"{root} は ECOBuild が作った作業空間（{_workspaces.AREA}/<名前>）ではないので閉じません。",
                                hint=f"自分で作った作業ツリーなら git worktree remove \"{root}\" で外してください。")
        if (lock := _locks.status(root)).locked:   # --discard-local でも閉じない（使っている最中の作業空間）
            raise EcoBuildError(ErrorCode.WORKSPACE_LOCKED, "作業空間が使用中（ロック中）のため、閉じられません。",
                                hint=_locked_hint(cls.command), details=[r.text for r in lock.reasons])
        module = cls(root, _config.load(root / _config.FILE_NAME), github=github)
        reasons = module.before_close_workspace(root)
        if reasons:
            raise EcoBuildError(ErrorCode.WORKSPACE_LOCKED, "作業空間が使用中のため、閉じられません。",
                                hint="使っているものを止めてから、もう一度実行してください。", details=list(reasons))
        if not discard_local:
            module._check_nothing_unpushed()
        if dry_run:
            return WorkspaceClosed(root, done=False)
        if linked:
            return cls._remove_worktree(root)
        try:
            aside = _set_aside([root])
        except EcoBuildError:   # 使われていて動かせない：その場で、消せるものだけを消す
            left = _remove_contents(root)
            _workspaces.forget(root)
            return WorkspaceClosed(root, removed=False, left=left)
        try:
            remove_tree(aside[0][1])
        except OSError:
            left = _remove_contents(aside[0][1])
            if left:   # 移した後で他のプログラムが使い始めた（まれ）。元の場所に戻して、残ったものを知らせる
                _put_back(aside)
                _workspaces.forget(root)
                return WorkspaceClosed(root, removed=False, left=left)
            with contextlib.suppress(OSError):
                aside[0][1].rmdir()
        _workspaces.forget(root)
        return WorkspaceClosed(root)

    @staticmethod
    def _remove_worktree(root: Path) -> WorkspaceClosed:
        """作業空間（git worktree）root を消す：脇へ移してから（使用中なら動かせないので、何も消さずに断る）、git の記録を
        外して中身を消す。"""
        git = _Git(_Git(root).common_root())
        git.run("worktree", "unlock", str(root), check=False)
        try:
            aside = _set_aside([root])
        except EcoBuildError as error:   # 使用中：何も変えずに断る
            git.run("worktree", "lock", "--reason", _LOCK_REASON, str(root), check=False)
            raise EcoBuildError(ErrorCode.IN_USE, f"作業空間 {root} は、他のプログラムが使っているため消せません。",
                                hint="エディター・端末・エクスプローラー等でそのフォルダーを開いていれば閉じてから、もう一度"
                                     "実行してください。", details=error.details) from None
        moved = aside[0][1]
        try:
            remove_tree(moved)
        except OSError:
            if _remove_contents(moved):   # 移した後で他のプログラムが使い始めた（まれ）。元の場所に戻して断る
                _put_back(aside)
                git.run("worktree", "lock", "--reason", _LOCK_REASON, str(root), check=False)
                raise EcoBuildError(ErrorCode.IN_USE, f"作業空間 {root} は、他のプログラムが使っているため消せません。",
                                    hint="エディター・端末等でそのフォルダーを開いていれば閉じてから、もう一度実行してください。")
            with contextlib.suppress(OSError):
                moved.rmdir()
        git.run("worktree", "prune", check=False)   # フォルダーがなくなった記録を片付ける
        return WorkspaceClosed(root)

    def before_close_workspace(self, path: Path) -> list[str]:
        """作業空間 path を閉じられないわけ（使っているもの。なければ空）。本体はない：拡張（エージェント等）が、動いている
        ものを理由にする。"""
        return []

    @classmethod
    def _recorded_workspaces(cls, full_name: str, github: _github.GitHub) -> list["Module"]:
        """このPCに記録した、full_name の元の clone と前の版の作業空間（今あるもの。作業空間は元の clone の中にある）。"""
        found = []
        for path in [item.path for item in _workspaces.recorded()] + _workspaces.legacy():
            if not (path / _config.FILE_NAME).is_file():
                continue
            try:
                url = _Git(path).get_config("remote.origin.url") or ""
            except Exception:   # gitで読めない（壊れたclone 等）
                continue
            name = _workspaces.github_name(url)
            if name is not None:
                if name.casefold() != full_name.casefold():
                    continue
            else:   # GitHubのものでない URL（ミラー等）は、GitHubに名前を聞く
                try:
                    if github.repository_name(path).casefold() != full_name.casefold():
                        continue
                except WorkError:
                    continue
            try:
                found.append(cls(path, _config.load(path / _config.FILE_NAME), github=github))
            except EcoBuildError:
                continue
        return found

    @staticmethod
    def _check_nothing_unpushed_in(modules: list["Module"]) -> None:
        """どの作業空間にも、手元にだけあるものがないことを確かめる（すべて見てから、まとめて知らせる）。"""
        found = []
        for module in modules:
            try:
                module._check_nothing_unpushed()
            except EcoBuildError as error:
                found += [f"{module.root}：{item}" for item in error.details or ()]
        if found:
            raise EcoBuildError(ErrorCode.UNFINISHED_WORK, "手元の作業空間に、GitHubにないものがあります。",
                                hint=_UNPUSHED_HINT, details=found)

    @staticmethod
    def _module_repository(name: str, github: _github.GitHub) -> _github.RepositoryInfo:
        info = github.get_repository(name)
        if not github.repository_has_file(info.full_name, _config.FILE_NAME):
            raise EcoBuildError(ErrorCode.NOT_IN_MODULE,
                                f"{info.full_name} はECOBuildのモジュールではありません（{_config.FILE_NAME} がありません）。",
                                hint="ECOBuildで作ったモジュールだけを扱えます。")
        return info

    def _check_nothing_unpushed(self) -> None:
        """手元にだけあるもの（未コミットの変更・GitHubにないコミット・退避）がないことを確かめる。依存先のcloneも、
        .ecobuild/ の中の作業空間（作業空間 .ecobuild/w/・前の版の作業役 等。閉じると一緒に消える）とその依存先も。

        作業空間（git worktree）はブランチと退避を元の clone・ほかの作業空間と共有するので、見るのは自分が取り出している
        もの（HEAD と、そのブランチで退避したもの）だけ。"""
        found = []
        roots = []
        for workspace in (self.root, *_workspaces.inside(self.root)):
            nested = (*workspace.glob("*/.git"), *workspace.glob("*/*/.git"))   # 依存先のclone（型が置く。deps/<名前> 等）
            roots += [workspace] + sorted(p.parent for p in nested)
        for root in roots:
            git = _Git(root)
            label = "" if root == self.root else f"{root.relative_to(self.root).as_posix()}："
            linked = git.is_linked_worktree()
            if git.output("status", "--porcelain"):
                found.append(f"{label}未コミットの変更")
            heads = ("HEAD",) if linked else ("--branches",)
            commits = git.output("log", *heads, "--not", "--remotes", "--format=%h %s") if git.rev_parse("HEAD") else ""
            if commits:
                found.append(f"{label}GitHubにないコミット {len(commits.splitlines())} 件")
            branch = git.current_branch()
            stashes = git.stash_list()
            if linked:
                stashes = [entry for entry in stashes if branch is not None and entry.branch == branch]
            if stashes:
                found.append(f"{label}退避した変更（stash）")
        if found:
            raise EcoBuildError(ErrorCode.UNFINISHED_WORK, f"作業空間 {self.root} に、GitHubにないものがあります。",
                                hint=_UNPUSHED_HINT, details=found)

    def cloned(self, dependencies: tuple[DependencyChange, ...]) -> ModuleCloned:
        return ModuleCloned(self.name, self.root, self.remote_url or "", self.project_names, dependencies)

    @property
    def remote_url(self) -> str | None:
        return self.repository.remote_url

    @property
    def project_names(self) -> tuple[str, ...]:
        """今あるProject（型が Project を持たない・読めなければ空）。"""
        try:
            return tuple(p.name for p in self.projects())
        except EcoBuildError:
            return ()

    def summary(self) -> ModuleCreated:
        return ModuleCreated(self.name, self.root, self.remote_url or "", self.project_names)

    # 作業の流れのうち、型・管理するファイル・確認が関わるもの（ほかは module.repository） ---------------

    def status(self, *, fetch: bool = False) -> ModuleStatus:
        """excluded：新しいファイルのうち、管理するファイルの対象外のもの（task commit が含めない）。
        dependencies：手元の版が記録と違う依存先（依存先の依存先も。dependency_mismatches）。
        format・latest_format：モジュールの仕様の版と、この ECOBuild の版（古ければ module upgrade）。"""
        status = self.repository.status(fetch=fetch)
        return ModuleStatus(**{f.name: getattr(status, f.name) for f in fields(status)} | {
            "excluded": tuple(p for p in status.untracked if not self.is_tracked(p)),
            "dependencies": self.dependency_mismatches(), "lock": _locks.status(self.root),
            "format": self.config.format, "latest_format": _config.FORMAT})

    def tasks(self, *, closed: bool = False, label: str | None = None, assignee: str | None = None,
              search: str | None = None, milestone: str | None = None, ready: bool = False,
              sort: str | None = None, sprint: str | None = None, submitted: bool = False,
              to_review: bool = False) -> list[wm.TaskSummary]:
        tasks = self.repository.tasks(closed=closed, label=label, assignee=assignee, search=search,
                                      milestone=milestone, ready=ready, sort=sort, sprint=sprint,
                                      submitted=submitted, to_review=to_review)
        paths = self.task_workspaces()
        return [replace(t, workspace=paths.get(t.number, t.workspace)) for t in tasks]

    def task_status(self, number: int | None = None) -> wm.TaskStatus:
        """タスクブランチの場所は、このPCの他の作業空間（task start で作ったもの等）も見る。"""
        status = self.repository.task_status(number)
        path = self.task_workspaces().get(status.number, status.workspace)
        task = None if status.task is None else replace(status.task, workspace=path)
        return replace(status, workspace=path, task=task)

    # 確認（他人の提出を確認用の作業空間に取り出す。依存先・生成ファイルもその記録に合わせる） ------------------

    def review(self, number: int) -> "Module":
        """タスク number の提出を、確認用の作業空間（<元の clone>/.ecobuild/w/r<PRの番号>。切り離された状態で、コミットは
        できない）に取り出し、その Module を返す。依存先・生成ファイルもその提出の記録に合わせる（作業空間の Module で）。
        既にあれば、提出の最新にする。取り出した結果（ReviewResult）は返した Module の reviewed。"""
        pr = self.repository.require_submission(number)
        self._exclude_workspaces()
        opened: list[Module] = []
        result = self.repository.review_in(pr.number, self.workspace_place(f"r{pr.number}"),
                                           open=self._opener(opened, local_from=self.workspace_root / _config.LOCAL_FILE_NAME))
        module = opened[0] if opened else self._open_workspace(result.workspace)
        module.reviewed = result
        return module

    def review_task(self, number: int) -> wm.ReviewResult:
        """タスクの提出を確認用の作業空間に取り出して確かめる（review の結果だけ）。"""
        return self.review(number).reviewed

    def end_review(self, number: int | None = None) -> wm.ReviewResult:
        """確認を終えて、確認用の作業空間を消す。number：確認しているPR（省略すると、この確認用の作業空間のもの）。"""
        return self.repository.end_review(number)

    # 提出と完了（番号はタスクの番号） -------------------------------------------------------

    def submit(self, *, title: str | None = None, partial: bool | None = None, draft: bool = False,
               reviewers: tuple[str, ...] = (), check: bool = True, note: str | None = None,
               verified_by: tuple[str, ...] = (), progress: Callable[[str], None] | None = None) -> wm.PullRequest:
        """タスクブランチを提出する：（check で確かめる）→ push → 提出（PR）。提出済みなら送り直し・下書きの付け外し。

        未コミットの変更（追跡中のファイル・管理するファイルに当たる新しいファイル）があれば止める。
        提出の本文に、確認の結果（どの版で何が通ったか。出し直しのたびに今の版のものへ）と、note（提出の説明。
        None なら提出済みの説明のまま）を書く。verified_by：提出した人が自分で確かめたこと（「<コマンド>=<結果>」。
        check を行わずに出すときの証拠。確認の節に並べる）。progress：経過（check の各項目等）を知らせる口。
        """
        verified = _verified_items(verified_by)
        task_branch = self.require_task_branch("提出")
        self._refuse_uncommitted("提出")
        mismatches = self.dependency_mismatches()
        if mismatches and not draft:
            raise EcoBuildError(ErrorCode.DEPENDENCY_NOT_RECORDED,
                                "手元の依存先が記録の版と違います（CIと取り込んだ後は記録の版を使います）："
                                + mismatch_text(mismatches),
                                hint=f"依存先の作業を先に完了し、{self.op('deps update')} で記録を進めてください"
                                     f"（依存先の依存先なら、直接 {self.op('deps add')}）。このまま出すなら --draft")
        if mismatches:
            (progress or _quiet)("注意：手元の依存先が記録の版と違います（CIは記録の版を使います）：" + mismatch_text(mismatches))
        saved = self._last_check()
        items = None if saved is None else tuple(CheckItem(**item) for item in saved.get("items", ()))
        settings = self.config.submit_checks
        if check and saved is None and not settings.items:
            (progress or _quiet)(f"提出の確認は設定していません（確認せずに出します。設定は {self.op('task checks')}）")
            items = ()
        elif check:
            if saved is not None:
                (progress or _quiet)("この版は確認済みです（ビルド・テストを省きます）")
            else:
                names = "・".join(CHECK_NAMES[name] for name in settings.items)
                (progress or _quiet)(f"確認しています（{names}）…")
                items = self.check(allow_dependency_mismatch=draft, only=settings.items, tests=settings.tests).items
                for item in items:
                    (progress or _quiet)(_check_line(item))
        checked_at = (self._last_check() or saved or {}).get("at")   # 今通したなら記録は新しい
        sections = {SUBMIT_CHECK_SECTION: self._check_section(items, checked_at, verified)}
        if note is not None:
            sections = {SUBMIT_NOTE_SECTION: note, **sections}
        return task_branch.submit(title=title, partial=partial, draft=draft, reviewers=reviewers, sections=sections)

    def _check_section(self, items: tuple[CheckItem, ...] | None, at: str | None,
                       verified: tuple[tuple[str, str], ...] = ()) -> str:
        """提出の本文の「確認」の節：今の版（HEAD）で通った check の項目と、いつ確かめたか。確かめていなければ、そう書く。

        verified（提出した人が自分で確かめたこと。(コマンド, 結果)）があれば、その後に並べる（ECOBuild は確かめていない）。
        """
        head = (self.repository.git.rev_parse("HEAD") or "")[:7]
        title = "### 確認（ECOBuild）"
        own = (["", "提出した人が確かめたこと（ECOBuild は確かめていません）：", "",
                *(f"- `{command}`：{result}" for command, result in verified)] if verified else [])
        if items is None:
            return "\n".join([f"{title}\n\nこの版（`{head}`）は `{self.op('check')}`（生成ファイル・衝突の印・ビルド・"
                              f"テスト）を行わずに提出しました{NO_CHECK_NOTE}。", *own])
        if not items:
            return "\n".join([f"{title}\n\nこの版（`{head}`）は、提出の確認を設定していないので確かめずに提出しました"
                              f"{NO_CHECKS_SET_NOTE}。", *own])
        profile = _config.load_local(self.root).get("profile")
        when = at or _dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        where = f"版 `{head}`" + (f"、ビルド設定 {profile}" if profile else "") + f"、{when}"
        lines = [f"- {_check_line(item)}" for item in items]   # 以前の記録（版だけ）なら項目はない
        return "\n".join([title, "", f"提出した人の手元で `{self.op('check')}` が通りました（{where}）。",
                          *([""] + lines if lines else []), *own])

    def finish(self, number: int | None = None, **options) -> wm.FinishResult:
        """タスクを完了する（ecowork の Repository.finish。wait・ignore_checks・subject・timeout）。

        タスクブランチを取り出していた作業空間は、タスクブランチと一緒に消える（中間提出なら残る）。消せなければ
        （使用中・新しいファイルがある等）残して知らせる（workspace_kept）。
        """
        current = self._current_task()
        if current is not None and number in (None, current):
            self._refuse_uncommitted("完了")
        return self.repository.finish(number, **options)

    def _current_task(self) -> int | None:
        task_branch = self.repository.current_task_branch()
        return None if task_branch is None else task_branch.number

    def _refuse_uncommitted(self, action: str) -> None:
        """未コミットの変更（追跡中のファイル・管理するファイルに当たる新しいファイル）があれば止める。"""
        tree = self.repository.git.working_tree()
        pending = list(dict.fromkeys(tree.staged + tree.unstaged + tree.conflicted
                                     + tuple(p for p in tree.untracked if self.is_tracked(p))))
        if pending:
            raise EcoBuildError(ErrorCode.DIRTY_WORKING_TREE, f"未コミットの変更があるため、{action}できません。",
                                hint=f"{self.op('task commit')} --message \"…\" で記録してから、もう一度実行してください。",
                                details=pending)

    # 共同作業者・ブランチの保護（複数人での開発） ----------------------------------------------

    def protect(self, *, approvals: int | None = None, require_ci: bool = False) -> _github.Protection:
        """作成元（default_base）を GitHub のブランチの保護で守る。approvals を省くと、[task] require_approval
        なら1、なければ0（PR は必須、承認は要らない）。"""
        if approvals is None:
            approvals = 1 if self.repository.require_approval else 0
        protection = self.repository.protect(approvals=approvals, require_ci=require_ci)
        if approvals and not self.repository.require_approval:
            self.repository.notices.append(
                "GitHub は承認のない取り込みを止めますが、管理者は越えられます。ECOBuild を使う全員に承認を必須にするなら、"
                ".ecobuild/ecobuild.toml の [task] に require_approval = true を書いてコミットしてください。")
        return protection

    # 管理するファイル（tracking） ---------------------------------------------------------

    def tracked_files(self) -> _tracking.TrackedFiles:
        """管理するファイル（新しいファイルのうち、task commit が自動で含めるもの）の一覧と出どころ。"""
        include, exclude = _tracking.module_lists(self.config.extra)
        patterns = [_tracking.TrackedPattern(p, _tracking.BUILT_IN_SOURCE) for p in _tracking.BUILT_IN]
        patterns += [_tracking.TrackedPattern(p, _tracking.TYPE_SOURCE, p in exclude)
                     for p in type(self.type).tracked_patterns()]
        patterns += [_tracking.TrackedPattern(p, _tracking.MODULE_SOURCE, p in exclude) for p in include]
        note = self.type.generated_note or ""
        return _tracking.TrackedFiles(tuple(patterns), exclude, note)

    def is_tracked(self, path: str) -> bool:
        """新しいファイルを、管理するファイルとして自動でコミットに含めるか。"""
        if self.type.is_managed(path) or path in self._created_files():
            return True
        listing = self.tracked_files()
        for item in listing.patterns:
            if item.excluded:
                continue
            if _tracking.matches(item.pattern, path) and (
                    item.source == _tracking.BUILT_IN_SOURCE
                    or not any(_tracking.matches(e, path) for e in listing.exclude)):
                return True
        return False

    def untracked_outside(self) -> tuple[str, ...]:
        """管理するファイルの対象外の新しいファイル（task commit が含めないもの）。"""
        return tuple(p for p in self.repository.git.working_tree().untracked if not self.is_tracked(p))

    def track(self, *patterns: str, remove: bool = False) -> _tracking.TrackedFiles:
        """管理するファイルのパターンを足す（remove：外す）。ecobuild.toml の [files] を変える（タスクブランチで）。

        外すとき、[files] include にあるものは include から消し、型の既定なら exclude に書く。
        """
        self.require_task_branch("管理するファイルの変更")
        patterns = tuple(dict.fromkeys(_tracking.normalize(p) for p in patterns if _tracking.normalize(p)))
        if not patterns:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "パターンを指定してください（例：\"*.txt\"）。")
        include, exclude = _tracking.module_lists(self.config.extra)
        defaults = type(self.type).tracked_patterns()
        for pattern in patterns:
            if remove:
                if pattern in _tracking.BUILT_IN:
                    raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{pattern} はECOBuildが管理するファイルなので外せません。")
                if pattern not in include and pattern not in defaults:
                    raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{pattern} は管理するファイルのパターンにありません。",
                                        hint=f"{self.op('track')} で一覧を確認できます。")
                include = tuple(p for p in include if p != pattern)
                if pattern in defaults and pattern not in exclude:
                    exclude += (pattern,)
            else:
                exclude = tuple(p for p in exclude if p != pattern)
                if pattern not in include and pattern not in defaults:
                    include += (pattern,)
        self._save_config(replace(self.config, extra=_tracking.with_lists(self.config.extra, include, exclude)))
        return self.tracked_files()

    def commit(self, message: str, paths: tuple[str, ...] = (), *, amend: bool = False) -> wm.RecordResult:
        """変更をコミットする（task commit）。パスなし：追跡中のファイルの変更・削除と、管理するファイルに当たる新しい
        ファイル。パスあり：そのパスだけ（対象外の新しいファイルも、名前を書いたものは含める）。"""
        task_branch = self.require_task_branch("コミット")
        if not message.strip() and not amend:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "コミットメッセージが空です。")
        outside = ()
        if paths:
            paths = tuple(p.replace("\\", "/").strip("/") or "." for p in paths)
            untracked = self.repository.git.working_tree().untracked
            outside = tuple(p for p in untracked
                            if any(r == "." or p == r or p.startswith(r + "/") for r in paths) and not self.is_tracked(p))
        result = task_branch.record(message, paths, include=self.is_tracked, amend=amend)
        self._forget_created(result.files)
        return replace(result, outside=outside)

    # ECOBuild 自身のファイル（.ecobuild の中と、型の管理ファイル・生成ファイル）。変わったら何でもコミットするのではなく、
    # それを変えるのが目的の操作（リンク・提出の前の作り直し等）だけが、その操作のメッセージでコミットする
    # （2026-10-19 ユーザーの指示）。ほかの操作（Project の設定等）の変更は、作業者が task commit でコミットする。

    def is_own_file(self, path: str) -> bool:
        """ECOBuild 自身のファイルか（.ecobuild の中〔無視するものは git に出てこない〕と、型の管理ファイル）。"""
        path = path.replace("\\", "/").strip("/")
        return path.startswith(_config.DIRECTORY + "/") or self.type.is_managed(path)

    def own_changes(self) -> dict[str, tuple[int, int] | None]:
        """未コミットの ECOBuild 自身のファイルと、その中身の印（大きさ・更新時刻。消したなら None）。
        操作の前後で比べ、その操作が書き換えたファイルを知る（commit_own_changes）。"""
        tree = self.repository.git.working_tree()
        changes: dict[str, tuple[int, int] | None] = {}
        for path in {*tree.staged, *tree.unstaged, *tree.untracked, *tree.conflicted}:
            if self.is_own_file(path):
                try:
                    stat = (self.root / path).stat()
                    changes[path] = (stat.st_size, stat.st_mtime_ns)
                except OSError:
                    changes[path] = None
        return changes

    def commit_own_changes(self, message: str, before: dict) -> wm.RecordResult | None:
        """操作が書き換えた ECOBuild 自身のファイル（before〔own_changes〕から変わったもの）だけを、message で
        コミットする（しなければ None。Push はしない）。前からあった未コミットの変更は、作業者のものとして残す。
        コミットするのはタスクブランチで、確認中・取り込み中・衝突の解決中でないときだけ。
        """
        changed = tuple(sorted(p for p, mark in self.own_changes().items() if before.get(p, ...) != mark))
        if not changed:
            return None
        task_branch = self.repository.current_task_branch()
        git = self.repository.git
        if task_branch is None or self.repository._reviewing() is not None or git.is_merging() or git.working_tree().conflicted:
            return None
        result = task_branch.record(message, changed)
        self._forget_created(result.files)
        self.repository.notices.append(f"「{message}」としてコミットしました（{result.sha[:7]}。Push はしていません）。")
        return result

    def relative_path(self, path: Path | str, cwd: Path | str) -> str:
        """cwd からの相対・絶対パスを、モジュールのルートからの相対パス（/ 区切り）にする（CLIの引数用）。"""
        candidate = Path(path)
        absolute = candidate if candidate.is_absolute() else Path(cwd) / candidate
        try:
            return absolute.resolve().relative_to(self.root.resolve()).as_posix() or "."
        except ValueError:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{path} はモジュールの外です。") from None

    def _created_record(self) -> Path:
        return self.root / self.repository.git.output("rev-parse", "--git-path", "ecobuild-created")

    def _created_files(self) -> set[str]:
        """ECOBuildのコマンド（file add・project add 等）が作った、まだコミットしていないファイル。"""
        try:
            return set(self._created_record().read_text(encoding="utf-8").splitlines())
        except OSError:
            return set()

    def _created(self, changed):
        """ECOBuildのコマンドが作ったファイルを、管理するファイルの対象外でも commit に含めるために覚える。"""
        changes = changed if isinstance(changed, list) else [changed]
        created = {p for c in changes for p in c.paths if (self.root / p).is_file()}
        known = self._created_files()
        if created - known:
            self._created_record().write_text("\n".join(sorted(known | created)) + "\n", encoding="utf-8")
        return changed

    def _forget_created(self, committed: tuple[str, ...]) -> None:
        remaining = self._created_files() - set(committed)
        record = self._created_record()
        if remaining:
            record.write_text("\n".join(sorted(remaining)) + "\n", encoding="utf-8")
        else:
            record.unlink(missing_ok=True)

    # タスクブランチ・最新化・退避（型に手元をそろえさせる・設定を読み直す） ---------------------------------

    def start_task(self, number: int, *, account: str | None = None, base: str | None = None, name: str | None = None,
                   ignore_blocked: bool = False, take_over: bool = False) -> "Module":
        """タスクを始める：タスクブランチを作業空間（<元の clone>/.ecobuild/w/<番号>）に取り出し、依存先と生成ファイルを
        用意して、その作業空間の Module を返す。この場所（元の clone 等）のブランチは変えない。既にほかの作業空間が
        そのタスクブランチを取り出していれば、そこを返す。account：その作業空間を動かす GitHub のアカウント。

        依存先の clone（他のモジュールの中。型が置く deps/ 等）では、今までどおりその場でタスクブランチに切り替えて、
        この Module を返す（依存先の作業版）。
        """
        if _workspaces.nested(self.root) and not self.repository.git.is_linked_worktree():
            if account:
                self.repository.use_account(account)
            self.repository.task(number).start(base=base, name=name, ignore_blocked=ignore_blocked,
                                               take_over=take_over)
            return self
        return self.start_task_in(number, self.workspace_place(str(number)), base=base, name=name,
                                  ignore_blocked=ignore_blocked, take_over=take_over, account=account)

    def start_task_in(self, number: int, place: Path | str, *, base: str | None = None, name: str | None = None,
                      ignore_blocked: bool = False, take_over: bool = False, account: str | None = None) -> "Module":
        """タスクブランチを作業空間（git worktree）として place に取り出し（ecowork の Repository.start_task_in）、
        依存先と生成ファイルを用意して、その作業空間の Module を返す。ふつうは start_task（場所は ECOBuild が決める）。

        準備（型の prepare）は作業空間のモジュールでだけ行う（ここの依存先・生成ファイルは変えない）。このPC用の設定
        （ecobuild.local.toml。コミットしない）は、新しい作業空間へ元の clone のものを写す。
        """
        self._exclude_workspaces()
        opened: list[Module] = []
        local = self.workspace_root / _config.LOCAL_FILE_NAME
        result = self.repository.start_task_in(number, place, base=base, name=name, ignore_blocked=ignore_blocked,
                                               take_over=take_over, account=account,
                                               open=self._opener(opened, local_from=local))
        return opened[0] if opened else self._open_workspace(result.workspace)

    def _opener(self, opened: list["Module"], *, local_from: Path | None = None) -> Callable[[Path], Repository]:
        """ecowork が作った作業空間の場所から、その Module を開いて Repository を返す口（開いた Module は opened に入れる）。
        local_from：まだこのPC用の設定がない作業空間に、写す設定ファイル。"""
        def open_workspace(root: Path) -> Repository:
            target = Path(root) / _config.LOCAL_FILE_NAME
            if local_from is not None and local_from.is_file() and not target.exists():
                with contextlib.suppress(OSError):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(local_from.read_bytes())
            opened.append(self._open_workspace(root))
            return opened[-1].repository
        return open_workspace

    def _exclude_workspaces(self) -> None:
        """作業空間の置き場所（.ecobuild/w/）を、元の clone の git に見せない（共通の info/exclude に1度だけ書く）。"""
        _workspaces.exclude_area(self.workspace_root)

    def require_task_branch(self, action: str) -> wm.TaskBranch:
        """ファイルを変える操作はタスクブランチでだけ（Module と型の約束。型の操作もここで確かめる）。"""
        return self.repository.require_task_branch(action)

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
                              f"{self.op('sync continue')} で管理ファイルから作り直します。")
            raise

    def continue_sync(self) -> SyncResult:
        """衝突を解決した後、止まっている取り込みを完了し、手元をそろえる。

        印のなくなったファイルは登録し、衝突した生成ファイルは（解決した）管理ファイルから作り直す。
        """
        if self.repository.git.is_merging() or self.repository.git.is_rebasing():
            self.repository.resolve_conflicts(skip=self.type.is_generated)
        self._regenerate_conflicted_files()
        return self._sync_result(self.repository.continue_sync())

    def abort_sync(self) -> None:
        self.repository.abort_sync()
        self._reload()

    def stash(self) -> wm.StashResult:
        result = self.repository.stash()
        self._reload()
        return result

    def stash_pop(self) -> wm.StashResult:
        try:
            return self.repository.stash_pop()
        finally:
            self._reload()

    def restore(self, *paths: str, staged: bool = False, source: str | None = None) -> wm.RestoreResult:
        """変更を取り消す。source：以前の版（コミット）の状態に戻す（タスクブランチで。未コミットの変更になる）。"""
        result = self.repository.restore(*paths, staged=staged, source=source)
        if source is None:
            self._reload()
        else:
            self._after_sync()        # 管理ファイルも戻ったら、生成ファイル・依存先をそろえる
        return result

    def reset_task(self, revision: str, *, keep: bool = False, dry_run: bool = False) -> wm.ResetResult:
        """タスクブランチを以前の版まで戻す（その後の、まだ push していないコミットを捨てる）。
        keep：ファイルはそのまま（捨てたコミットの変更は、コミットしていない変更として残る）。"""
        result = self.repository.reset_task(revision, keep=keep, dry_run=dry_run)
        if result.dropped and not dry_run and not keep:   # keep ではファイルが変わらないので、そろえ直すものもない
            self._after_sync()
        return result

    # 型の能力 ---------------------------------------------------------------------

    def _builds(self, operation: str) -> Builds:
        if not isinstance(self.type, Builds):
            raise self.type.not_supported(operation)
        return self.type

    def _projects(self, operation: str) -> HasProjects:
        if not isinstance(self.type, HasProjects):
            raise self.type.not_supported(operation)
        return self.type

    def _files(self, operation: str) -> HasFiles:
        if not isinstance(self.type, HasFiles):
            raise self.type.not_supported(operation)
        return self.type

    def _dependencies(self, operation: str) -> HasDependencies:
        if not isinstance(self.type, HasDependencies):
            raise self.type.not_supported(operation)
        return self.type

    # ビルド（型） -----------------------------------------------------------------

    def project_at(self, path: Path | str) -> str | None:
        """pathが属するProjectの名前。どのProjectにも属さなければNone（全体が対象）。"""
        return self.type.project_at(Path(path)) if isinstance(self.type, HasProjects) else None

    def executable_at(self, path: Path | str) -> str | None:
        """run の既定：pathが実行ファイルのProjectの中ならそれ、それ以外はNone（唯一の実行ファイル）。"""
        return self.type.executable_at(Path(path)) if isinstance(self.type, Builds) else None

    def build(self, *, project: str | None = None, configuration: str = "", profile: str | None = None,
              action: str = "build") -> BuildResult:
        """build・clean・rebuild。configurationを省略すると、名前付きビルド設定（なければ型の既定）の構成。"""
        options, name = self.build_options(configuration, profile)
        result = self._builds(action).build(project, options, action)
        return BuildResult(result.project, result.configuration, result.artifacts, name, result.action)

    def test(self, *, project: str | None = None, configuration: str = "", profile: str | None = None,
             tests: tuple[str, ...] = ()) -> TestResult:
        options, _ = self.build_options(configuration, profile)
        return self._builds("テスト").test(project, options, tuple(tests))

    def run(self, *, project: str | None = None, configuration: str = "", profile: str | None = None,
            arguments: str = "") -> RunResult:
        options, _ = self.build_options(configuration, profile)
        return self._builds("実行").run(project, options, arguments)

    # 名前付きビルド設定 ---------------------------------------------------------

    def build_options(self, configuration: str = "", profile: str | None = None):
        """使うビルド設定と、その名前。profileを省略すると、このPCで選んだ設定（ecobuild profile use）。"""
        name = profile or _config.load_local(self.root).get("profile")
        selected = None
        if name:
            if name not in self.config.profiles:
                raise EcoBuildError(ErrorCode.PROFILE_NOT_FOUND, f"ビルド設定 {name} はありません。",
                                    hint=f"{self.op('profile list')} で一覧、{self.op('profile add')} で追加できます。")
            selected = self.config.profiles[name]
        return self._builds("ビルド").build_options(selected, configuration), name

    def profiles(self) -> ProfileList:
        return ProfileList(dict(self.config.profiles), _config.load_local(self.root).get("profile"))

    def set_profile_project(self, name: str, project: str, values: dict | None) -> ProfileList:
        """ビルド設定 name の、Project ごとの上書きを変える（values が None なら外す）。"""
        self.require_task_branch("ビルド設定の変更")
        if name not in self.config.profiles:
            raise EcoBuildError(ErrorCode.PROFILE_NOT_FOUND, f"ビルド設定 {name} はありません。",
                                hint=f"{self.op('profile add')} {name} で先に作ってください。")
        if values is not None and project not in {p.name for p in self.projects()}:
            raise EcoBuildError(ErrorCode.PROJECT_NOT_FOUND, f"Project {project} はありません。")
        current = self.config.profiles[name]
        projects = {k: v for k, v in current.projects.items() if k != project}
        if values:
            projects[project] = dict(values)
        profile = replace(current, projects=dict(sorted(projects.items())))
        self._builds("ビルド設定").validate_profile(profile)
        self._save_config(self.config.with_profiles({**self.config.profiles, name: profile}))
        return self.profiles()

    def add_profile(self, name: str, profile: _config.Profile) -> ProfileList:
        self.require_task_branch("ビルド設定の追加")
        if not _NAME.fullmatch(name):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"ビルド設定の名前 {name!r} は使えません。",
                                hint="英字で始まり、英数字と _ だけからなる名前にしてください。")
        self._builds("ビルド設定").validate_profile(profile)
        self._save_config(self.config.with_profiles({**self.config.profiles, name: profile}))
        return self.profiles()

    def remove_profile(self, name: str) -> ProfileList:
        self.require_task_branch("ビルド設定の削除")
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
                                hint=f"{self.op('profile list')} で一覧を確認してください。")
        local = _config.load_local(self.root)
        local["profile"] = name
        _config.save_local(self.root, local)
        return self.profiles()

    # Project・ファイル（型） ---------------------------------------------------------

    def projects(self) -> tuple[ProjectSummary, ...]:
        return self._projects("Project の一覧").projects()

    def add_project(self, name: str, kind: str, *, link: str | None = None, test: bool = True) -> FilesChanged:
        """kind：library（test なら組のテスト用 <名前>Test も）・app・test・bench（link のライブラリをリンク）。"""
        self.require_task_branch("Projectの追加")
        if not _NAME.fullmatch(name):
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"Project名 {name!r} は使えません。",
                                hint="英字で始まり、英数字と _ だけからなる名前にしてください。")
        return self._created(self._projects("Project の追加").add_project(name, kind, link=link, test=test))

    def remove_project(self, name: str) -> FilesChanged:
        self.require_task_branch("Projectの削除")
        return self._projects("Project の削除").remove_project(name)

    # 保存する設定（型。管理ファイルが変わるので、変えるのはタスクブランチで） ------------------------------

    def module_settings(self) -> dict:
        return self.type.module_settings()

    def set_module_settings(self, **changes) -> dict:
        self.require_task_branch("モジュールの設定")
        return self.type.set_module_settings(**changes)

    # Project の設定・ファイル（型） ------------------------------------------------------

    def project_details(self, name: str) -> dict:
        return self._projects("Project の設定").project_details(name)

    def set_project(self, name: str, **changes) -> dict:
        self.require_task_branch("Projectの設定")
        return self._projects("Project の設定").set_project(name, **changes)

    def move_project(self, name: str, destination: str) -> FilesChanged:
        self.require_task_branch("Projectの移動")
        return self._created(self._projects("Project の移動").move_project(name, destination))

    def link_project(self, name: str, library: str, *, as_type: str | None = None) -> dict:
        """同じモジュールのライブラリをリンクする（他のモジュールは link）。"""
        self.require_task_branch("Projectのリンク")
        before = self.own_changes()
        result = self._projects("Project のリンク").link_project(name, library, as_type=as_type)
        self.commit_own_changes(f"{name} に {library} をリンク", before)
        return result

    def unlink_project(self, name: str, link: str) -> dict:
        self.require_task_branch("Projectのリンクの解除")
        before = self.own_changes()
        result = self._projects("Project のリンク").unlink_project(name, link)
        self.commit_own_changes(f"{name} から {link} のリンクを外す", before)
        return result

    def add_file(self, path: Path | str, *, test: bool = True, template: str | None = None) -> FilesChanged:
        """Projectにファイルを足す（テストを一緒に作るか等は型が決める）。template：使うファイルテンプレート。"""
        self.require_task_branch("ファイルの追加")
        return self._created(self._files("ファイルの追加").add_file(Path(path), test=test, template=template))

    def add_files(self, paths, *, test: bool = True, template: str | None = None) -> list[FilesChanged]:
        """複数のファイルをまとめて足す（C++：ヘッダーを先に作り、一緒に足したヘッダーをソースが読み込む）。"""
        self.require_task_branch("ファイルの追加")
        return self._created(self._files("ファイルの追加").add_files([Path(p) for p in paths], test=test, template=template))

    def remove_file(self, path: Path | str, *, test: bool = True) -> FilesChanged:
        self.require_task_branch("ファイルの削除")
        return self._files("ファイルの削除").remove_file(Path(path), test=test)

    def move_file(self, source: Path | str, destination: Path | str, *, test: bool = True) -> FilesChanged:
        self.require_task_branch("ファイルの移動")
        return self._created(self._files("ファイルの移動").move_file(Path(source), Path(destination), test=test))

    def add_test(self, path: Path | str, destination: Path | str | None = None, *, dry_run: bool = False) -> FilesChanged:
        """今あるファイルのテストを作る（C++：組のテスト用Projectの、同じ構成の場所に <名前>Test.cpp）。
        dry_run：作らずに、作る場所だけ（GUI が既定の場所を出すため）。"""
        files = self._files("テストの作成")
        if dry_run:
            return files.add_test(Path(path), Path(destination) if destination else None, dry_run=True)
        self.require_task_branch("テストの作成")
        return self._created(files.add_test(Path(path), Path(destination) if destination else None))

    # 依存先（型） -----------------------------------------------------------------

    def link(self, repository: str, *, project: str | None = None, shared: bool = False) -> LinkResult:
        """GitHubにあるモジュール（「名前」か「所有者/名前」）を依存先にする。"""
        self.require_task_branch("依存先のリンク")
        dependencies = self._dependencies("依存先")
        url = self.repository.github.get_repository(repository).clone_url
        before = self.own_changes()
        result = dependencies.link(url, project=project, shared=shared)
        self.commit_own_changes(f"{'・'.join(result.projects)} に {result.name}（{result.revision[:7]}）をリンク", before)
        return result

    def unlink(self, name: str) -> LinkResult:
        self.require_task_branch("依存先のリンクの解除")
        before = self.own_changes()
        result = self._dependencies("依存先").unlink(name)
        self.commit_own_changes(f"{result.name} のリンクを外す", before)
        return result

    def dependencies(self, *, fetch: bool = False, all: bool = False) -> tuple[DependencyState, ...]:
        """依存先の状態。fetch：GitHubの側も確かめる（まだあるか・アーカイブ・名前の変更・新しい版）。
        all：依存先の依存先も（via に記録している依存先）。"""
        if all:
            states = self.type.all_dependencies() if isinstance(self.type, HasDependencies) else ()
        else:
            states = self._direct_dependencies()
        return tuple(self._remote_dependency(d) for d in states) if fetch else states

    def dependency_mismatches(self) -> tuple[DependencyState, ...]:
        """手元の版が記録と違う依存先（作業版・未コミットの変更・別の版。依存先の依存先も）。

        手元のビルドはこの版を使うが、CI や他の人は記録の版を使うので、結果が食い違う（実用試験 D-1）。
        """
        try:
            states = self.dependencies(all=True)
        except EcoBuildError:
            return ()   # 依存先を読めない（構成の途中など）。ここでは知らせない
        return tuple(d for d in states if d.state in ("working", "modified", "differs"))

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
        return self._dependencies("依存先").dependency_tree()

    def update_dependencies(self, name: str | None = None) -> tuple[DependencyChange, ...]:
        """依存先の記録を、GitHubの最新にする（I-018）。"""
        self.require_task_branch("依存先の更新")
        before = self.own_changes()
        result = self._dependencies("依存先").update_dependencies(name)
        self.commit_own_changes(f"依存先 {name} を最新に" if name else "依存先を最新に", before)
        return result

    def sync_dependencies(self) -> tuple[DependencyChange, ...]:
        """手元の依存先を記録の版に合わせる（作業版・変更のあるものは触らない）。"""
        return self.type.sync_dependencies() if isinstance(self.type, HasDependencies) else ()

    def _direct_dependencies(self) -> tuple[DependencyState, ...]:
        """直接の依存先（型が依存先を持たなければ空）。"""
        return self.type.dependencies() if isinstance(self.type, HasDependencies) else ()

    # 文書・CI・確認 -------------------------------------------------------------

    def upgrade(self, *, dry_run: bool = False) -> ModuleUpgraded:
        """モジュールを今の ECOBuild の仕様に合わせる（ecobuild.toml の format を今の版にする）。

        版ごとの移行（_MIGRATIONS：置き場所の変更等）を順に行ったうえで、ECOBuild が作ったファイルを今の中身にする：
        .gitignore・.gitattributes（足りない行を足す。足した行は残す）、拡張が置くファイル（environment_files。なければ置く）、
        .ecobuild/README.md（なければ置き、あれば作り直す）、AGENTS.md・CIのワークフロー（あれば作り直す。
        手で編集したワークフローは作り直さず skipped に）、型の生成ファイル（型の refresh）。README は書き換えない。
        この作業空間の git の設定も、clone するときと同じにする（改行コードの扱い〔ecowork の CLONE_CONFIG〕。コミットしない。
        以前に clone した作業空間で、改行コードだけの差が出ないように）。
        今の版でも同じことをする（同じ版の中で変わった分もそろう）。
        変えたファイルは「ECOBuild の更新」としてコミットする（人の作業ではないので、どのブランチでもよい。タスクブランチでなければ
        GitHub へ push もする。タスクブランチなら、いつもの Push・提出に乗る）。未コミットの変更があれば止める（混ざらないように）。
        dry_run：変えるファイルを返すだけ（版ごとの移行と型の生成ファイルの分は、行うまで分からないので含まない）。
        """
        if not dry_run:
            self.repository.check_own_commit("モジュールの更新")
        start = self.config.format
        before = set(self._changed_paths())
        if not dry_run:
            for version in range(start, _config.FORMAT):
                if version in _MIGRATIONS:
                    _MIGRATIONS[version](self)
        planned, skipped = self._ecobuild_files()
        if start != _config.FORMAT:
            planned[_config.FILE_NAME] = ""   # 版を書き換える（中身は保存のときに作る）
        git_config = self._missing_git_config()
        if dry_run:
            return ModuleUpgraded(start, _config.FORMAT, tuple(sorted(planned)), tuple(skipped), dry_run=True,
                                  git_config=git_config)
        for setting in git_config:
            self.repository.git.set_config(*setting.split("=", 1))
        for path, text in planned.items():
            if path != _config.FILE_NAME:
                (self.root / path).parent.mkdir(parents=True, exist_ok=True)
                (self.root / path).write_text(text, encoding="utf-8", newline="\n")
        self._save_config(replace(self.config, format=_config.FORMAT))
        self.type.refresh()
        changed = tuple(sorted((set(self._changed_paths()) - before) | set(planned)))
        if not changed:
            return ModuleUpgraded(start, _config.FORMAT, changed, tuple(skipped), git_config=git_config)
        commit, branch, pushed = self.repository.commit_own(changed, UPGRADE_MESSAGE)
        return ModuleUpgraded(start, _config.FORMAT, changed, tuple(skipped), commit=commit, branch=branch, pushed=pushed,
                              git_config=git_config)

    def _missing_git_config(self) -> tuple[str, ...]:
        """clone するときの git の設定（CLONE_CONFIG）のうち、この作業空間の設定（--local）と違うもの。"""
        git = self.repository.git
        return tuple(s for s in _CLONE_CONFIG if git.get_config(s.split("=", 1)[0]) != s.split("=", 1)[1])

    def _ecobuild_files(self, *, rewrite: bool = True) -> tuple[dict[str, str], list[str]]:
        """ECOBuild が作るファイルのうち、今の中身と違うもの（場所 → 新しい中身）と、手で編集してあるため作り直さないもの。

        .gitignore・.gitattributes は足りない行を足し、拡張が置くファイルはなければ置く。rewrite：ECOBuild が作った
        AGENTS.md・CI のワークフローを作り直す（module adopt では、元からあるファイルなので作り直さない）。
        """
        planned: dict[str, str] = {}
        skipped = []
        type_class = type(self.type)
        for path, wanted in ((f"{_config.DIRECTORY}/.gitignore", GITIGNORE),
                             (f"{_config.DIRECTORY}/.gitattributes", GITATTRIBUTES),
                             (".gitignore", type_class.gitignore()), (".gitattributes", type_class.gitattributes())):
            current = self._read(path)
            merged = _with_lines(current, wanted)
            if merged != current:
                planned[path] = merged
        for path, text in self.environment_files(type_class).items():   # なければ置く（あればモジュールのもの。変えない）
            if not (self.root / path).exists():
                planned[path] = text
        planned[_docs.ECOBUILD_README] = _docs.ecobuild_readme(self.config, type_class)   # ECOBuild の持ち物（なければ置く）
        if rewrite and (self.root / "AGENTS.md").is_file():
            planned["AGENTS.md"] = _docs.agents(self.config, type_class)
        workflow_path = self.root / _docs.CI_WORKFLOW
        if rewrite and workflow_path.is_file():
            if _docs.ci_edited(workflow_path.read_text(encoding="utf-8")):
                skipped.append(_docs.CI_WORKFLOW)
            elif (workflow := self.type.ci_workflow(self.config)) is not None:
                planned[_docs.CI_WORKFLOW] = _docs.stamp_ci(workflow)
        review_path = self.root / _ci_review.REVIEW_WORKFLOW
        if rewrite and review_path.is_file() and self.config.ci.review:   # 見直しのワークフローも、あれば今の中身に
            if _docs.ci_edited(review_path.read_text(encoding="utf-8")):
                skipped.append(_ci_review.REVIEW_WORKFLOW)
            else:
                planned[_ci_review.REVIEW_WORKFLOW] = _docs.stamp_ci(_ci_review.workflow(self.config.ci))
        return {p: text for p, text in planned.items() if self._read(p) != text}, skipped

    def _read(self, path: str) -> str:
        file = self.root / path
        return file.read_text(encoding="utf-8") if file.is_file() else ""

    def _changed_paths(self) -> tuple[str, ...]:
        tree = self.repository.git.working_tree()
        return (*tree.staged, *tree.unstaged, *tree.untracked)

    def write_agents(self) -> FilesChanged:
        """AGENTS.md（エージェント向けの使い方）を作り直す。"""
        self.require_task_branch("AGENTS.md の作成")
        (self.root / "AGENTS.md").write_text(_docs.agents(self.config, type(self.type)), encoding="utf-8",
                                             newline="\n")
        return FilesChanged("agent init", ("AGENTS.md",))

    def agent_guide(self) -> AgentGuide:
        """エージェント向けの作業の手順。AGENTS.md はこれを読むよう案内する（タスクブランチでなくても読める）。"""
        return AgentGuide(_docs.agent_guide(self.config, type(self.type)))

    def write_ci(self, settings: _config.CiSettings | None = None, *, force: bool = False) -> CiInitResult:
        """GitHub Actions のワークフロー（中身は型が用意する）を、CIの設定（[ci]）から作る。

        settings を渡すと [ci] に保存してから作る。手で編集したワークフロー（作ったときの印と内容が合わない）は、
        force がなければ上書きしない。非公開の依存先は、CIの GITHUB_TOKEN では取得できない。その依存先を返す。
        """
        self.require_task_branch("CIの設定の作成")
        path = self.root / _docs.CI_WORKFLOW
        if path.is_file() and not force and _docs.ci_edited(path.read_text(encoding="utf-8")):
            raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{_docs.CI_WORKFLOW} は手で編集されています。",
                                hint="上書きしてよければ --force を付けてください（編集した内容は失われます）。")
        new_config = self.config if settings is None else self.config.with_ci(settings)
        review_path = self.root / _ci_review.REVIEW_WORKFLOW
        if (new_config.ci.review and review_path.is_file() and not force
                and _docs.ci_edited(review_path.read_text(encoding="utf-8"))):
            raise EcoBuildError(ErrorCode.ALREADY_EXISTS, f"{_ci_review.REVIEW_WORKFLOW} は手で編集されています。",
                                hint="上書きしてよければ --force を付けてください（編集した内容は失われます）。")
        workflow = self.type.ci_workflow(new_config)
        if workflow is None:
            raise self.type.not_supported("CI")
        if new_config is not self.config:
            self._save_config(new_config)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_docs.stamp_ci(workflow), encoding="utf-8", newline="\n")
        review = self._write_review(new_config.ci)
        private = []
        for dependency in self._direct_dependencies():
            name = dependency.url.removesuffix(".git").split("github.com/")[-1]
            try:
                if self.repository.github.is_private(name):
                    private.append(dependency.name)
            except Exception:  # GitHub以外・見つからない等は案内しない
                continue
        return replace(review, path=_docs.CI_WORKFLOW, private_dependencies=tuple(private))

    def _write_review(self, ci: _config.CiSettings) -> CiInitResult:
        """見直しのワークフローを、設定（[ci] の review）に合わせて作る・消す。作ったら、要るシークレットがあるかも見る。"""
        path = self.root / _ci_review.REVIEW_WORKFLOW
        if not ci.review:
            if path.is_file():
                path.unlink()
                return CiInitResult("", (), removed=(_ci_review.REVIEW_WORKFLOW,))
            return CiInitResult("", ())
        path.write_text(_docs.stamp_ci(_ci_review.workflow(ci)), encoding="utf-8", newline="\n")
        secret = _ci_review.AUTH[ci.review_auth][0]
        try:
            missing = secret not in self.repository.github.list_secrets(self.root)
        except Exception:  # 読めない（権限・GitHub に届かない）なら案内だけ
            missing = False
        return CiInitResult("", (), _ci_review.REVIEW_WORKFLOW, secret, missing)

    def remove_ci(self) -> FilesChanged:
        """CI（ecobuild ci init で作ったワークフロー）をやめる。"""
        self.require_task_branch("CIの設定の削除")
        path = self.root / _docs.CI_WORKFLOW
        if not path.is_file():
            raise EcoBuildError(ErrorCode.FILE_NOT_FOUND, f"{_docs.CI_WORKFLOW} はありません。")
        path.unlink()
        removed = [_docs.CI_WORKFLOW]
        review = self.root / _ci_review.REVIEW_WORKFLOW
        if review.is_file():   # 見直しも CI の一部（設定の [ci] の review は残すので、ci init で戻る）
            review.unlink()
            removed.append(_ci_review.REVIEW_WORKFLOW)
        return FilesChanged("ci remove", tuple(removed))

    def ci_state(self) -> CiState:
        """CIの設定（[ci]）と、ワークフローのファイルの状態（ある・手で編集した・今の設定のとおり）。"""
        path = self.root / _docs.CI_WORKFLOW
        text = path.read_text(encoding="utf-8") if path.is_file() else None
        workflow = self.type.ci_workflow(self.config)
        settings = self.config.ci
        review_path = self.root / _ci_review.REVIEW_WORKFLOW
        review_text = review_path.read_text(encoding="utf-8") if review_path.is_file() else None
        return CiState(_docs.CI_WORKFLOW, workflow is not None, text is not None,
                       text is not None and _docs.ci_edited(text),
                       text is not None and workflow is not None and text == _docs.stamp_ci(workflow),
                       settings.os, settings.configurations, settings.shared, settings.branches, self.config.default_base,
                       settings.review, settings.review_auth, _ci_review.REVIEW_WORKFLOW, review_text is not None,
                       review_text == _docs.stamp_ci(_ci_review.workflow(settings)) if settings.review
                       else review_text is None, _ci_review.AUTH[settings.review_auth][0])

    def ci_dispatch(self, branch: str | None = None) -> str:
        """今いるブランチ（または branch）で、ECOBuildのCIを手動で実行する。"""
        return self.repository.ci_dispatch(Path(_docs.CI_WORKFLOW).name, branch)

    def check(self, *, build: bool = True, allow_dependency_mismatch: bool = False,
              only: tuple[str, ...] | None = None, tests: tuple[str, ...] = ()) -> CheckReport:
        """PRを出す前の確認：生成ファイル・衝突の印・依存先・ビルド・テスト。失敗があれば check_failed。

        コミットの前に使ってよい：生成ファイルは最新にし、未コミットなら知らせるだけ（コミットは task submit が確かめる）。
        依存先：手元の版が記録と違えば失敗（手元では通っても CI は記録の版を使う）。allow_dependency_mismatch なら知らせるだけ。
        only：行う項目だけ（提出の確認の設定 [check] submit。config.SUBMIT_CHECK_ITEMS）。None なら全部。tests：test で
        流す試験（空なら全部）。全部を行って通ったときだけ、通った版として残す（task submit が繰り返さないため）。
        """
        if only is not None:
            _config.validate_submit_checks(_config.SubmitChecks(items=only))
        wanted = (lambda name: True) if only is None else (lambda name: name in only)
        items = []
        if wanted("generated"):
            items += self._check_generated()
        git = self.repository.git
        if wanted("conflict_markers"):
            task_branch = self.repository.current_task_branch()
            markers = git.conflict_markers("HEAD")
            if task_branch is not None and git.rev_parse(f"origin/{task_branch.base}"):
                markers += git.conflict_markers(f"origin/{task_branch.base}...HEAD")
            items.append(CheckItem("conflict_markers", not markers, ", ".join(dict.fromkeys(markers))))
        if only is None:
            excluded = self.untracked_outside()
            if excluded:   # 知らせるだけ（わざと置いているものもあるので、失敗にしない）
                items.append(CheckItem("excluded", True, f"{len(excluded)} 個はコミットに含めません："
                                                         + ", ".join(excluded)))
            eol = git.eol_only("HEAD") if git.rev_parse("HEAD") else ()
            if eol:   # 知らせるだけ（task commit は自動で含めない。中身は変わっていない）
                items.append(CheckItem("eol_only", True, f"{len(eol)} 個は改行コード（CRLF と LF）だけが違います"
                                                         f"（task commit は含めません。git の改行の設定は "
                                                         f"{self.op('module upgrade')} で clone と同じにできます）："
                                                         + ", ".join(eol)))
            mismatches = self.dependency_mismatches()
            if mismatches:
                items.append(CheckItem("dependencies", allow_dependency_mismatch,
                                       "記録の版と違います（CIは記録の版を使います）：" + mismatch_text(mismatches)))
        if build:
            steps = (("build", lambda: self.build()), ("test", lambda: self.test(tests=tests)))
            for name, action in (step for step in steps if wanted(step[0])):
                try:
                    result = action()
                    detail = f"成功 {result.passed}" if name == "test" else ""
                    items.append(CheckItem(name, True, detail))
                except EcoBuildError as error:
                    if error.code == ErrorCode.NOT_SUPPORTED and not (name == "test" and tests):
                        continue  # ビルド・テストのない型（流す試験を指定したのに絞れない型は失敗にする）
                    items.append(CheckItem(name, False, error.message))
                    break
        report = CheckReport(tuple(items))
        if only is None and not tests:   # 一部だけの確認は、全部を通った記録を消しも残しもしない
            self._record_check(report, report.ok and build)
        if not report.ok:
            raise EcoBuildError(ErrorCode.CHECK_FAILED, "確認で問題が見つかりました：" +
                                "、".join(i.name for i in items if not i.ok),
                                hint=f"内容を直して、もう一度 {self.op('check')} を実行してください。",
                                details=[{"name": i.name, "ok": i.ok, "detail": i.detail} for i in items])
        return report

    def set_submit_checks(self, settings: _config.SubmitChecks) -> _config.SubmitChecks:
        """提出の前に行う確認（[check]）を変える。ecobuild.toml を変えるので、タスクブランチでだけ（コミットして提出）。"""
        self.require_task_branch("提出の確認の設定")
        self._save_config(self.config.with_submit_checks(settings))
        return self.config.submit_checks

    def _check_generated(self) -> list[CheckItem]:
        try:
            self.type.refresh()
            pending = self._uncommitted_managed_files()
            return [CheckItem("generated", True, f"最新です（未コミット {len(pending)} ファイル。"
                                                 f"{self.op('task commit')} でコミットに含めてください）" if pending else "")]
        except EcoBuildError as error:
            return [CheckItem("generated", False, error.message)]

    def checked(self) -> bool:
        """今の版が、ビルド・テストを含む check を通ったままか（task submit --check で繰り返さないため）。"""
        return self._last_check() is not None

    def _last_check(self) -> dict | None:
        """今の版で通った check の記録（key・items）。なければ・版が変わっていれば None。"""
        key = self._check_key()
        record = self._check_record()
        if key is None or not record.is_file():
            return None
        text = record.read_text(encoding="utf-8").strip()
        try:
            saved = json.loads(text)
        except ValueError:
            saved = {"key": text}   # 以前の形（版だけ）
        return saved if isinstance(saved, dict) and saved.get("key") == key else None

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

    def _record_check(self, report: CheckReport, passed: bool) -> None:
        """通った check を版（_check_key）と項目ごとに残す（task submit が省く判断と、提出の本文の確認の節に使う）。"""
        record = self._check_record()
        key = self._check_key() if passed else None
        if key is None:
            record.unlink(missing_ok=True)
        else:
            items = [{"name": i.name, "ok": i.ok, "detail": i.detail} for i in report.items]
            at = _dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
            record.write_text(json.dumps({"key": key, "at": at, "items": items}, ensure_ascii=False) + "\n", encoding="utf-8")

    def _save_config(self, module_config: _config.ModuleConfig) -> None:
        _config.save(module_config, self.root / _config.FILE_NAME)
        self.config = module_config

    @staticmethod
    def _sync_result(result: wm.SyncResult) -> SyncResult:
        dependencies, regenerated = result.extra if result.extra is not None else ((), False)
        return SyncResult(result.branch, result.merged, dependencies, regenerated)

    def _after_sync(self) -> PrepareResult:
        """Git操作（切り替え・取り込み・確認の開始と終了・取り消し）の後：設定を読み直し、型に手元をそろえさせる。"""
        self._reload()
        return self.type.prepare()

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
            self.type = self.registry.load(new_config.type, command=self.command)(self)
        self.config = new_config
        self.repository.default_base = new_config.default_base
        self.repository.require_approval = _require_approval(new_config)

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
        """生成ファイルを作り直し、作り直して変わったファイルはそれだけでコミットする。ほかに生成・管理ファイルの
        未コミットの変更が残れば止める（task submit の前）。"""
        before = self.own_changes()
        if not self.type.refresh():
            return
        self.commit_own_changes("生成ファイルを作り直す（提出の前）", before)
        changed = self._uncommitted_managed_files()
        if changed:
            raise EcoBuildError(
                ErrorCode.GENERATED_FILES_OUTDATED,
                f"{self.type.generated_note or '生成ファイル'}・管理ファイルがコミットされていません。",
                hint=f"{self.op('task commit')} --message \"…\" でコミットしてから再実行してください。",
                details=changed,
            )

    def __repr__(self) -> str:
        return f"Module({self.name!r}, {str(self.root)!r})"


SUBMIT_NOTE_SECTION = "note"     # 提出の本文の節（ecowork の with_section）：提出の説明
SUBMIT_CHECK_SECTION = "check"   # 確認の結果
NO_CHECK_NOTE = "（--no-check）"   # 確認の節の、check を行わずに提出した印（submitted_check が読む）
NO_CHECKS_SET_NOTE = "（確認の設定なし）"   # 提出の確認（[check] submit）が空なので確かめなかった印
CHECK_NAMES = {"generated": "生成ファイル", "conflict_markers": "衝突の印", "excluded": "管理しないファイル",
               "eol_only": "改行コードだけの差", "dependencies": "依存先", "build": "ビルド", "test": "テスト"}
_MISMATCH_STATES = {"working": "作業版", "modified": "未コミットの変更あり", "differs": "記録と別の版"}


def submitted_check(body: str) -> tuple[bool | None, str | None]:
    """提出（PR）の本文の確認の節から：(check を通して提出したか〔--no-check なら False。節がない・確認を設定して
    いないなら None〕, その版〔コミットの頭。読めなければ None〕)。"""
    text = wm.section(body, SUBMIT_CHECK_SECTION)
    if text is None or NO_CHECKS_SET_NOTE in text:
        return None, None
    version = re.search(r"`([0-9a-f]{7,40})`", text)
    return NO_CHECK_NOTE not in text, version.group(1) if version else None


def _verified_items(values: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """提出の --verified-by（「<コマンド>=<結果>」）を (コマンド, 結果) に分ける。= がない・どちらかが空なら誤り。"""
    items = []
    for value in values:
        command, sep, result = value.partition("=")
        if not sep or not command.strip() or not result.strip():
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT,
                                f"確かめたことは「<コマンド>=<結果>」の形で書きます：{value}",
                                hint='例：--verified-by "pytest tests/unit=成功 12"')
        items.append((command.strip(), result.strip()))
    return tuple(items)


def mismatch_text(states) -> str:
    """記録と違う依存先を「STL（作業版 task/7、EcoMath 経由）」の形で並べる。"""
    def one(d) -> str:
        notes = [_MISMATCH_STATES.get(d.state, d.state) + (f" {d.branch}" if d.branch else "")]
        if d.via:
            notes.append(f"{d.via} 経由")
        return f"{d.name}（{'、'.join(notes)}）"
    return "、".join(one(d) for d in states)


def _check_line(item: CheckItem) -> str:
    """check の1項目を「OK ビルド」「NG テスト：…」の形で。"""
    return f"{'OK' if item.ok else 'NG'} {CHECK_NAMES.get(item.name, item.name)}" + (f"：{item.detail}" if item.detail else "")


def _quiet(message: str) -> None:
    pass


# module new の経過：最初に作るもの（型の new_kinds）ごとの言い方
_POPULATING = {"app": "実行できるものを用意中…", "library": "ライブラリとテストを用意中…", "none": "モジュールの中身を用意中…"}


def _require_approval(config: _config.ModuleConfig) -> bool:
    """ecobuild.toml の [task] require_approval（完了の前に承認を必須にする）。既定は false。"""
    value = config.extra.get("task", {}).get("require_approval", False)
    if not isinstance(value, bool):
        raise EcoBuildError(ErrorCode.INVALID_CONFIG, "[task] の require_approval は真偽値です（true／false）。")
    return value


def _module_type_of(text: str | None) -> str:
    """ecobuild.toml の中身から、モジュールの型（読めなければ空）。"""
    try:
        value = tomllib.loads(text or "").get("module", {}).get("type")
    except tomllib.TOMLDecodeError:
        return ""
    return value if isinstance(value, str) else ""


def _github_state(github: _github.GitHub, name: str) -> tuple[str, str | None]:
    """GitHubのリポジトリの今：ok・archived・moved（名前が変わった。今の名前も返す）・gone（ない）・unknown。"""
    try:
        info = github.get_repository(name)
    except WorkError as error:
        return ("gone" if error.code == ErrorCode.REPOSITORY_NOT_FOUND else "unknown"), None
    if info.full_name.casefold() != name.casefold():
        return "moved", info.full_name
    return ("archived" if info.archived else "ok"), None


def _set_aside(roots: list[Path]) -> list[tuple[Path, Path]]:
    """消すフォルダーを、同じ場所の別の名前へ移す（Windowsでは、他のプログラムが使っているフォルダーは移せない）。
    1つでも移せなければ、移したものを戻して IN_USE。"""
    moved = []
    for root in roots:
        target = root.with_name(f".{root.name}.deleting")
        number = 1
        while target.exists():
            number += 1
            target = root.with_name(f".{root.name}.deleting{number}")
        try:
            root.rename(target)
        except OSError as error:
            _put_back(moved)
            raise EcoBuildError(ErrorCode.IN_USE, f"手元のclone {root} は、他のプログラムが使っているため削除できません。",
                                hint="Visual Studio・エディター・端末・エクスプローラー等でそのフォルダーを開いていれば閉じてから、"
                                     "もう一度実行してください（GitHubのリポジトリはまだ削除していません）。",
                                details=str(error)) from None
        moved.append((root, target))
    return moved


def _put_back(moved: list[tuple[Path, Path]]) -> None:
    for original, target in reversed(moved):
        with contextlib.suppress(OSError):
            target.rename(original)


def _remove_contents(root: Path) -> tuple[str, ...]:
    """root の中身を、消せるものだけ消す。消せずに残ったもの（root からの相対パス）を返す。"""
    for child in list(root.iterdir()) if root.is_dir() else []:
        with contextlib.suppress(OSError):
            if child.is_dir() and not child.is_symlink():
                remove_tree(child)
            else:
                child.chmod(0o666)
                child.unlink()
    if not root.is_dir():
        return ()
    return tuple(sorted(p.relative_to(root).as_posix() for p in root.iterdir()))


def _empty_directory(path: Path) -> bool:
    try:
        return not any(path.iterdir())
    except OSError:
        return False
