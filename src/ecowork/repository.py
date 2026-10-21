"""リポジトリ：作業の対象（GitHubのリポジトリ＋手元のclone）と、作業の進め方。

タスクブランチ＝Issue＝task/<番号> のブランチ。コミットはタスクブランチでだけ行い、
タスクブランチでないブランチ（main・develop等）への変更はPRのマージでだけ入る。

このファイルには、作成・状態・ブランチ・タスクブランチ・内部の処理を置く。分野ごとの処理（タスクの管理・確認・履歴・CI・
提出と完了・共同作業者・最新化）は _tasks.py 等にあり、Repository がそれらを継承する。
"""

from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from ecotask import board as _board
from ecotask import tracker as _tracker
from . import git as _git
from . import github as _github
from . import hooks as _hooks
from . import model as wm
from .errors import ErrorCode, WorkError, operation
from ._lock import Locking
from ._tasks import TaskManagement
from ._review import Reviewing
from ._history import History
from ._ci import Ci
from ._completion import Completion
from ._members import Members
from ._access import ACCOUNT_KEY, Permissions
from ._sync import Syncing
from ._shared import _REVIEW_KEY, _github_name


class Hooks:
    """作業の流れの途中に、利用側の処理を入れる口。既定は何もしない。"""

    def after_sync(self, repository: "Repository") -> object:
        """sync・sync continue で取り込みが終わった後（衝突で止まったときは呼ばない）。

        戻り値は SyncResult.extra に入る。
        """
        return None

    def after_switch(self, repository: "Repository") -> None:
        """タスクブランチの作成・切り替え・片付け等で、手元の内容（ブランチ）が変わった後。

        依存先の版の記録等が変わることがあるため、利用側が手元を合わせる口（sync の after_sync と同じ考え方）。
        """

    def before_submit(self, repository: "Repository") -> None:
        """タスクブランチの反映（submit）で、pushする前。止めるときは WorkError を投げる。"""

    def unusable(self, repository: "Repository", refs: list[str]) -> dict[str, str]:
        """手元をその内容にできないもの（ref → 理由）。refs はブランチ・コミット。タスクブランチを作る起点・切り替え先を
        確かめ、ブランチの一覧に添える（例：ECOBuild ではモジュールでないブランチ）。既定はすべてできる。"""
        return {}

    def switch_locks(self, repository: "Repository") -> list[str]:
        """この作業空間でブランチを切り替えるのを止める理由（日本語の文。なければ空）。使用中の作業空間を守る口。"""
        return []

    def branch_locks(self, repository: "Repository", branch: str) -> list[str]:
        """タスクブランチ branch を消すのを止める理由：それを使っている（今のブランチにしている）、ロック中の
        ほかの作業空間（場所を添えた文。この作業空間は含めない。なければ空）。"""
        return []


class Repository(Locking, TaskManagement, Reviewing, History, Ci, Completion, Members, Permissions, Syncing):
    def __init__(
        self,
        root: Path | str,
        *,
        github: _github.GitHub | None = None,
        default_base: str = "main",
        command: str = "",
        hooks: Hooks | None = None,
        legacy_board: str | None = None,
        require_approval: bool = False,
    ):
        """
        default_base：作成元を省略したときのブランチ。
        command：ヒントに書くCLIのコマンド名（errors.operation）。
        github：試験でGitHubへの接続を差し替えるためのもの。
        legacy_board：以前の設定でつないでいたボードのURL（計画の情報の置き場所として引き継ぐ。ecotask の Tracker）。
        require_approval：完了（finish）の前に、提出の承認を必須にする。
        """
        self.root = Path(root)
        self.default_base = default_base
        self.require_approval = require_approval
        # 新しいファイルのうち、作業の一部（未コミットの変更）として扱うもの。None ならすべて。利用側が決める
        # （ecobuild：管理するファイル）。当たらないもの（メモ等）は、タスクブランチの切り替え等を止めない
        self.include_new: Callable[[str], bool] | None = None
        self.command = command
        self.hooks = hooks if hooks is not None else Hooks()
        self.tracker = _tracker.Tracker(self.root, github=github if github is not None else _github.default(),
                                        command=command, legacy_board=legacy_board)
        self.tracker.work_states = self._current_work_states
        self.git = _git.Git(self.root, command=command)
        self._use_bound_account()

    @property
    def github(self) -> _github.GitHub:
        return self.tracker.github

    @github.setter
    def github(self, value: _github.GitHub) -> None:
        self.tracker.github = value

    @property
    def notices(self) -> list[str]:
        """操作は成功したが、知らせておくこと（親タスクの子がすべて閉じた等）。CLIは結果と一緒に表示する。"""
        return self.tracker.notices

    @classmethod
    def create(
        cls,
        name: str,
        *,
        directory: Path | str = ".",
        description: str = "",
        private: bool = True,
        owner: str | None = None,
        populate: Callable[[Path], None] | None = None,
        message: str = "リポジトリを作成",
        github: _github.GitHub | None = None,
        default_base: str = "main",
        command: str = "",
        hooks: Hooks | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> "Repository":
        """GitHubリポジトリを作ってcloneし、populateで用意したファイルを初回コミットとしてpushする。
        progress：経過（今している作業）を知らせる口。"""
        report = progress or _quiet
        root = Path(directory).resolve() / name
        if root.exists():
            raise WorkError(ErrorCode.ALREADY_EXISTS, f"{root} は既に存在します。")
        github = github if github is not None else _github.default()
        report("GitHubにリポジトリを作成中…")
        repository = github.create_repository(name, owner=owner, private=private, description=description)
        try:
            report(f"{repository.full_name} をclone中…")
            repo = _git.clone(repository.clone_url, root)
            repo.run("symbolic-ref", "HEAD", f"refs/heads/{default_base}")
            if populate is not None:
                populate(root)
            report("初回のコミットを作成中…")
            repo.add(all=True)
            repo.commit(message, allow_empty=populate is None)
            report("GitHubへpush中…")
            repo.push(default_base, set_upstream=True)
            _hooks.install(repo.hooks_directory())
        except WorkError as error:
            error.hint = (error.hint + "\n" if error.hint else "") + (
                f"GitHubのリポジトリ {repository.full_name} は作成済みです。"
                f"やり直す場合は、リポジトリと {root} を削除してから実行してください。"
            )
            raise
        return cls(root, github=github, default_base=default_base, command=command, hooks=hooks)

    @classmethod
    def clone(
        cls,
        name: str,
        *,
        directory: Path | str = ".",
        github: _github.GitHub | None = None,
        default_base: str = "main",
        command: str = "",
        hooks: Hooks | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> "Repository":
        """GitHubのリポジトリ（「名前」か「所有者/名前」）を directory/<名前> へcloneする。progress：経過を知らせる口。"""
        report = progress or _quiet
        github = github if github is not None else _github.default()
        report("GitHubのリポジトリを確認中…")
        info = github.get_repository(name)
        root = Path(directory).resolve() / info.full_name.split("/")[-1]
        if root.exists():
            raise WorkError(ErrorCode.ALREADY_EXISTS, f"{root} は既に存在します。",
                            hint="別の場所で実行するか、既にあるcloneを使ってください。")
        report(f"{info.full_name} をclone中…")
        repo = _git.clone(info.clone_url, root)
        _hooks.install(repo.hooks_directory())
        return cls(root, github=github, default_base=default_base, command=command, hooks=hooks)

    def install_hooks(self) -> tuple[str, ...]:
        """タスクブランチでないブランチへの直接のコミット・pushを止めるフックを入れる（hooks）。"""
        return _hooks.install(self.git.hooks_directory())

    @property
    def remote_url(self) -> str | None:
        return self.git.get_config("remote.origin.url")

    # 状態 -----------------------------------------------------------------

    def status(self, *, fetch: bool = False) -> wm.Status:
        """fetch：GitHubの最新を取得してから調べる（作成元の遅れも数える）。"""
        archived = None
        if fetch:
            self.git.fetch()
            archived = self.check_repository(notify_archived=False)   # 状態の表示に含める
        tree = self.git.working_tree()
        task_branch = self.current_task_branch()
        pull_request = None
        finished = False
        if task_branch is not None:
            pulls = self.github.pull_requests_for_branch(self.root, task_branch.branch)
            if pulls:
                pull_request = self._submission_state(max(pulls, key=lambda p: p.number))
            if tree.upstream_gone:
                finished = self.github.get_issue(self.root, task_branch.number).state == "closed"
        reviewing = self._reviewing()
        return wm.Status(
            branch=tree.branch,
            task=None if task_branch is None else task_branch.number,
            base=None if task_branch is None else task_branch.base,
            staged=tree.staged, unstaged=tree.unstaged, untracked=tree.untracked, conflicted=tree.conflicted,
            ahead=tree.ahead, behind=tree.behind, merging=self.git.is_merging(), pull_request=pull_request,
            upstream_gone=tree.upstream_gone, reviewing=reviewing,
            base_behind=self._base_behind(task_branch) if fetch and task_branch is not None else None,
            archived=archived, reviewing_task=None if reviewing is None else self._task_of_pull_request(reviewing),
            finished=finished,
        )

    def _submission_state(self, info: _github.PullRequestInfo) -> wm.PullRequestState:
        pr = wm.PullRequest._from(self, info)
        return wm.PullRequestState(info.number, info.url, info.state, info.draft, pr.partial, info.base)

    def check_repository(self, *, notify_archived: bool = True) -> bool | None:
        """GitHubで（ECOBuildの外で）変わったリポジトリの状態を確かめ、知らせる。fetch の後に呼ぶ。

        - アーカイブ（読み取り専用）されている：知らせる。push・PR等はできない
        - 名前（所有者）が変わった：手元の origin を新しい名前に合わせる（GitHubの転送に頼らない）
        - タスクブランチの既定の作成元がGitHubにない：GitHubの既定のブランチを添えて知らせる
        アーカイブされているかを返す（GitHubに問い合わせられなければ None）。
        """
        try:
            current = self.github.repository_name(self.root)
            info = self.github.get_repository(current)
        except WorkError as error:
            self.notices.append(f"GitHubのリポジトリの状態を確かめられませんでした（{error.message}）。")
            return None
        if info.archived and notify_archived:
            self.notices.append(f"GitHubのリポジトリ {info.full_name} はアーカイブ（読み取り専用）されています。"
                                f"push・PR・タスクの変更はできません（元に戻すには {self._op('module unarchive')} "
                                f"{info.full_name}）。")
        url = self.remote_url or ""
        recorded = _github_name(url)
        if recorded is not None and recorded.casefold() != info.full_name.casefold():
            self.git.set_config("remote.origin.url", url.replace(recorded, info.full_name))
            self.notices.append(f"GitHubでリポジトリの名前が {recorded} から {info.full_name} に変わっていたため、"
                                "手元の origin を合わせました。")
        if self.git.remote_branches() and not self.git.has_remote_branch(self.default_base):
            default = self.github.default_branch(self.root)
            self.notices.append(f"タスクブランチの既定の作成元 {self.default_base} がGitHubにありません（GitHubで名前を変えたか、"
                                f"削除した可能性があります。GitHubの既定のブランチは {default}）。"
                                "モジュールの設定の作成元を合わせてください。")
        return info.archived

    def _base_behind(self, task_branch: wm.TaskBranch) -> int | None:
        base = f"{_git.REMOTE}/{task_branch.base}"
        return self.git.count(f"HEAD..{base}") if self.git.rev_parse(base) else None

    def _reviewing(self) -> int | None:
        value = self.git.get_config(_REVIEW_KEY)
        return int(value) if value else None

    # ブランチ ---------------------------------------------------------------

    def branches(self) -> list[wm.Branch]:
        """ブランチの一覧。開いている提出があれば、その状態と取り込み先も添える。"""
        self.git.fetch(reuse=True)
        local = set(self.git.local_branches())
        remote = set(self.git.remote_branches())
        opened = {i.head: i for i in sorted(self.github.list_pull_requests(self.root, closed=False),
                                            key=lambda i: i.number)}
        names = sorted(local | remote)
        unusable = self.hooks.unusable(self, [f"{_git.REMOTE}/{n}" if n in remote else n for n in names])
        result = []
        for name in names:
            branch = self._branch(name, name in local, name in remote)
            reason = unusable.get(f"{_git.REMOTE}/{name}" if name in remote else name)
            info = opened.get(name)
            if reason is not None:
                branch = replace(branch, unusable=reason)
            result.append(branch if info is None else replace(branch, submission=self._submission_state(info),
                                                              submitted_to=info.base))
        return result

    def branch(self, name: str) -> wm.Branch:
        self.git.fetch()
        local, remote = self.git.has_local_branch(name), self.git.has_remote_branch(name)
        if not (local or remote):
            raise WorkError(ErrorCode.BRANCH_NOT_FOUND, f"ブランチ {name} がありません。")
        return self._branch(name, local, remote)

    def create_branch(self, name: str, *, base: str | None = None) -> wm.Branch:
        """タスクブランチでないブランチを作り、GitHubへ反映する。"""
        if wm.is_task_branch(name):
            raise WorkError(
                ErrorCode.RESERVED_BRANCH_NAME,
                f"{wm.TASK_BRANCH_PREFIX} で始まる名前はタスクブランチ専用です。",
                hint=f"タスクブランチは {self._op('task start')} <Issue番号> で作ります。",
            )
        self.require_admin("ブランチの作成")
        start = self._base_start_point(base)
        if self.git.has_local_branch(name) or self.git.has_remote_branch(name):
            raise WorkError(ErrorCode.ALREADY_EXISTS, f"ブランチ {name} は既にあります。")
        self.git.create_branch(name, start, switch=False)
        self.git.push(name, set_upstream=True)
        return self._branch(name, True, True)

    # タスクとタスクブランチ ---------------------------------------------------------

    def clone_to(self, directory: Path | str, *, open: Callable[[Path], "Repository"] | None = None,
                 account: str | None = None) -> "Repository":
        """このリポジトリ（origin）を directory へもう1つcloneする（新しい作業空間。ブランチは作成元〔default_base〕）。

        open：cloneした場所から、そのcloneを操作する Repository を作る（利用側のフックをclone先に結び付ける）。
        省略するとフックなし。この Repository のフックは元のcloneに結び付いているため、clone先には渡さない。
        account：新しい作業空間を、そのアカウントとして動かす（use_account）。
        """
        target, url = self._new_clone(directory)
        if account and hasattr(self.github, "with_account"):
            self.github.with_account(account).identity(self.root)   # ログインしていなければ clone する前に止める
        other = self._clone_into(target, url, open, self._clone_base(None))
        if account:
            other.use_account(account)
        return other

    def clone_task_branch(self, number: int, directory: Path | str, *, base: str | None = None, name: str | None = None,
                          open: Callable[[Path], "Repository"] | None = None,
                          ignore_blocked: bool = False, take_over: bool = False,
                          account: str | None = None) -> "Repository":
        """新しい作業空間（clone）にタスクブランチを作る（I-007）。directoryは新しく作るcloneの場所。open・account は
        clone_to と同じ（account なら、そのアカウントとしてタスクを始める：担当者もそのアカウント）。"""
        target, url = self._new_clone(directory)
        task = self.task(number)  # Issueがあるか、担当者が他の人でないか、先に確かめる（clone する前に）
        if account is None:
            self.tracker.check_assignee(number, take_over=take_over)
        elif task.assignees and account not in task.assignees and not take_over:
            raise WorkError(ErrorCode.ASSIGNED_TO_OTHER, f"#{number} は {', '.join(task.assignees)} が担当しています。",
                            hint="重ねて作業しないよう、担当者と相談してください。引き継ぐなら --take-over。",
                            details=list(task.assignees))
        if account and hasattr(self.github, "with_account"):
            self.github.with_account(account).identity(self.root)   # ログインしていなければ clone する前に止める
        # 取り出すのは作成元。タスクブランチ（子タスクの親のもの等）は start が決めるので、clone は default_base で
        other = self._clone_into(target, url, open, self._clone_base(None if base and wm.is_task_branch(base) else base))
        if account:
            other.use_account(account)
        other.task(number).start(base=base, name=name, ignore_blocked=ignore_blocked,
                                 **({"take_over": True} if account and take_over else {}))
        return other

    def _new_clone(self, directory: Path | str) -> tuple[Path, str]:
        target = Path(directory).resolve()
        if target.exists():
            raise WorkError(ErrorCode.ALREADY_EXISTS, f"{target} は既に存在します。")
        url = self.remote_url
        if url is None:
            raise WorkError(ErrorCode.GIT_ERROR, "GitHubのリポジトリ（origin）が設定されていません。")
        return target, url

    def _clone_base(self, base: str | None) -> str:
        """新しい作業空間の clone で取り出すブランチ：作成元（base、なければ default_base）。必ず指定して取り出す：
        GitHub の既定のブランチ（main 等）が作成元とは限らない（module adopt は今のブランチをモジュールにする）。
        GitHub になければ、既定のブランチで代えずに止める。"""
        base = base or self.default_base
        if not self.git.has_remote_branch(base):
            self.git.fetch()
            if not self.git.has_remote_branch(base):
                raise WorkError(ErrorCode.BRANCH_NOT_FOUND, f"作成元のブランチ {base} が GitHub にありません。",
                                hint="作業空間は作成元のブランチから作ります。作成元を push するか、ある作成元を指定してください"
                                     "（branch list）。")
        return base

    def _clone_into(self, target: Path, url: str, open: Callable[[Path], "Repository"] | None,
                    branch: str) -> "Repository":
        _hooks.install(_git.clone(url, target, branch=branch).hooks_directory())
        try:
            if open is not None:
                other = open(target)
            else:
                other = type(self)(target, github=self.github, default_base=self.default_base, command=self.command)
        except Exception:
            _remove_tree(target)   # 今cloneしたもの（開けなければ作りかけ。残すと同じ場所でやり直せない）
            raise
        other.notices[:0] = self.notices
        return other

    def create_task(self, title: str, *, body: str = "", labels: tuple[str, ...] = (),
                    assignees: tuple[str, ...] = (), parent: int | None = None, blocked_by: tuple[int, ...] = (),
                    milestone: str | None = None, plan: dict[str, str | None] | None = None) -> wm.Task:
        """タスク（Issue）を作る。parent：親タスク、blocked_by：先に終わるべきタスク、milestone：題名、
        plan：計画の値（役割 → 値。due・planned_start・planned_end 等。ecotask の Tracker.create と同じ）。"""
        return wm.Task._from(self, self.tracker.create(title, body=body, labels=labels, assignees=assignees,
                                                       parent=parent, blocked_by=blocked_by, milestone=milestone,
                                                       plan=plan))

    def task(self, number: int) -> wm.Task:
        return wm.Task._from(self, self.github.get_issue(self.root, number))

    def current_task_branch(self) -> wm.TaskBranch | None:
        branch = self.git.current_branch()
        number = None if branch is None else wm.task_number(branch)
        if number is None:
            return None
        base = self.git.get_config(wm.base_key(branch)) or self.default_base
        return wm.TaskBranch(number, branch, base, self)

    def require_task_branch(self, action: str) -> wm.TaskBranch:
        task_branch = self.current_task_branch()
        if task_branch is None:
            raise WorkError(
                ErrorCode.NOT_ON_TASK_BRANCH,
                f"{action}はタスクブランチ（task/<番号>のブランチ）でだけ行えます。",
                hint=f"{self._op('task start')} <Issue番号> でタスクブランチを作るか、タスクブランチへ切り替えてください。",
            )
        return task_branch

    # ECOBuild 自身が変えてコミットするもの（モジュールの更新）。人の作業ではないので、タスクブランチでなくてもよい。
    def check_own_commit(self, action: str) -> None:
        """ECOBuild 自身のコミットの前の確認。自分が変えたものだけをコミットするので、未コミットの変更・取り込みの途中・
        提出の確認中・ブランチのない状態では止める。タスクブランチでなければ push もするので、GitHub に遅れていれば止める。"""
        if self._reviewing() is not None or self.git.current_branch() is None:
            raise WorkError(ErrorCode.PROTECTED_BRANCH, f"提出の確認中・ブランチのない状態では、{action}はできません。",
                            hint=f"{self._op('task review --done')} で戻ってから実行してください。")
        if self.git.is_merging():
            raise WorkError(ErrorCode.MERGE_CONFLICT, f"取り込みの途中なので、{action}はできません。",
                            hint=f"{self._op('sync continue')} か {self._op('sync abort')} で終えてから実行してください。")
        tree = self.git.working_tree()
        if tree.staged or tree.unstaged or tree.conflicted:
            raise WorkError(ErrorCode.DIRTY_WORKING_TREE, f"未コミットの変更があるため、{action}はできません（変更が混ざらないように）。",
                            hint=f"変更をコミットするか、{self._op('stash')} で退避するか、元に戻してから実行してください。")
        if self.current_task_branch() is None and self.git.has_remote_branch(tree.branch or ""):
            self.git.fetch()
            if self.git.working_tree().behind:
                raise WorkError(ErrorCode.NOT_FAST_FORWARD, f"GitHub の {tree.branch} に手元にないコミットがあります。",
                                hint=f"{self._op('sync')} で取り込んでから実行してください。")

    def commit_own(self, paths: tuple[str, ...], message: str) -> tuple[str, str, bool]:
        """ECOBuild 自身が変えたファイルをコミットする（check_own_commit の後で）。タスクブランチでなければ GitHub へ push する
        （タスクブランチならいつもの Push・提出に乗る）。返り値：(コミット, ブランチ, push したか)。"""
        branch = self.git.current_branch() or ""
        self.git.add(paths, all=True)
        commit = self.git.commit(message)
        if self.current_task_branch() is not None:
            return commit, branch, False
        try:
            self.git.push(branch)
        except WorkError as error:
            raise WorkError(error.code, f"「{message}」を {branch} にコミットしましたが、GitHub へ push できませんでした（{error.message}）。",
                            hint="ブランチを保護していると直接の push は断られます。コミットは手元に残っています。",
                            details=error.details) from error
        return commit, branch, True

    def pull_request(self, number: int | None = None) -> wm.PullRequest:
        """PRを返す。番号を省略すると、今のタスクブランチの開いているPR。"""
        if number is not None:
            return wm.PullRequest._from(self, self.github.get_pull_request(self.root, number))
        task_branch = self.require_task_branch("番号を省略したPRの指定")
        pulls = [p for p in self.github.pull_requests_for_branch(self.root, task_branch.branch) if p.state == "open"]
        if not pulls:
            raise WorkError(ErrorCode.NO_PULL_REQUEST, f"{task_branch.branch} の開いているPRがありません。",
                            hint=f"{self._op('task submit')} でPRを作成してください。")
        return wm.PullRequest._from(self, max(pulls, key=lambda p: p.number))

    # 内部 -----------------------------------------------------------------

    def _op(self, name: str) -> str:
        return operation(self.command, name)

    def _dirty(self) -> bool:
        """未コミットの変更があるか（新しいファイルは include_new に当たるものだけを数える）。"""
        tree = self.git.working_tree()
        return bool(tree.staged or tree.unstaged or tree.conflicted
                    or any(self.include_new is None or self.include_new(p) for p in tree.untracked))

    def _stash_messages(self) -> tuple[str, ...]:
        return tuple(entry.message for entry in self.git.stash_list())

    def _in_progress_error(self) -> WorkError:
        return WorkError(
            ErrorCode.MERGE_CONFLICT,
            "前回の取り込みが衝突で止まっています。",
            hint=f"ファイルを直して {self._op('sync continue')} で続けるか、"
                 f"{self._op('sync abort')} でやめてください。",
            details=list(self.git.working_tree().conflicted),
        )

    def _refuse_conflict_markers(self, markers: tuple[str, ...], *, committed: bool = False) -> None:
        """衝突の印が残っていれば止める（gitは印が残ったままでも登録・コミットできてしまう）。"""
        if not markers:
            return
        then = (f"{self._op('task commit')} でコミットしてから、もう一度実行してください" if committed
                else "もう一度実行してください")
        raise WorkError(
            ErrorCode.CONFLICT_MARKERS,
            f"衝突の印（<<<<<<< 等）が残っています（{len(markers)} か所）。",
            hint=f"印の場所を直して {then}。",
            details=list(markers),
        )

    def _unsafe_to_remove(self, branch: str) -> str | None:
        """消すと失われるコミット（作成元にもマージ済みのPRにも入っていないもの）があれば理由を返す。

        GitHubにpush済みでも、マージしていなければ消さない（片付けは反映したタスクブランチだけが対象）。
        """
        base = self.git.get_config(wm.base_key(branch)) or self.default_base
        remote = self.git.has_remote_branch(branch)
        if not self._lost_commits(branch, base, local=True, remote=remote):
            return None
        tip = self.git.rev_parse(branch)
        pushed = remote and self.git.is_ancestor(tip, f"{_git.REMOTE}/{branch}")
        number = wm.task_number(branch)
        return ("マージしていないコミットがあります" if pushed else "GitHubにないコミットがあります") + \
            f"（捨てる場合は {self._op('task drop')} {number}）"

    def _merged_heads(self, branch: str) -> list[str]:
        """マージ済みのPRの最後のコミット。別のcloneでpushされて手元にないものは、GitHubのPRの参照から取得する。"""
        heads = []
        for pull in self.github.pull_requests_for_branch(self.root, branch):
            if pull.state != "merged" or not pull.head_sha:
                continue
            if self.git.rev_parse(pull.head_sha) is None:
                self.git.run("fetch", "--quiet", _git.REMOTE, f"pull/{pull.number}/head", check=False)
            if self.git.rev_parse(pull.head_sha) is not None:
                heads.append(pull.head_sha)
        return heads

    def _lost_commits(self, branch: str, base: str, *, local: bool, remote: bool) -> tuple[str, ...]:
        """タスクブランチを消すと失われるコミット（作成元にも、マージ済みのPRにも入っていないもの）の件名。"""
        tips = ([branch] if local else []) + ([f"{_git.REMOTE}/{branch}"] if remote else [])
        kept = [f"{_git.REMOTE}/{base}" if self.git.has_remote_branch(base) else base]
        kept += self._merged_heads(branch)
        kept = [ref for ref in kept if self.git.rev_parse(ref)]
        return tuple(self.git.output("log", "--format=%s", *tips, "--not", *kept).splitlines())

    def _switch_to_latest(self, name: str) -> None:
        if self.git.has_local_branch(name):
            self.git.switch(name)
            if self.git.has_remote_branch(name):
                self.git.merge(f"{_git.REMOTE}/{name}", ff_only=True)
        else:
            self.git.create_branch(name, f"{_git.REMOTE}/{name}", switch=True)
            self.git.set_upstream(name)
        self.hooks.after_switch(self)

    def _submit_task_branch(self, task_branch: wm.TaskBranch, *, title: str | None, partial: bool | None,
                          draft: bool = False, reviewers: tuple[str, ...] = (),
                          sections: dict[str, str] | None = None) -> wm.PullRequest:
        self.hooks.before_submit(self)
        self.git.fetch()
        base_ref = f"{_git.REMOTE}/{task_branch.base}"
        if (self.git.count(f"{base_ref}..{task_branch.branch}") == 0
                or not self.git.has_changes(base_ref, task_branch.branch)):
            raise WorkError(ErrorCode.NOTHING_TO_SUBMIT, f"{task_branch.base} へ反映する変更がありません。",
                            hint=f"変更を {self._op('task commit')} で記録してから再実行してください。")
        self._refuse_conflict_markers(self.git.conflict_markers(f"{base_ref}...{task_branch.branch}"), committed=True)
        task_branch.push()
        opened = [p for p in self.github.pull_requests_for_branch(self.root, task_branch.branch) if p.state == "open"]
        if not opened:
            return self._create_submission(task_branch.number, task_branch.branch, task_branch.base, title=title,
                                           partial=bool(partial), draft=draft, reviewers=reviewers,
                                           sections=sections or {})
        # 提出済み：pushしたコミットがそのまま加わる（差し戻しの後の出し直し等）。下書き・題名・レビュアー・
        # 中間提出か（partial が None ならそのまま）・本文の節（渡したものだけ）を合わせる
        latest = max(opened, key=lambda p: p.number)
        if sections or (partial is not None and wm.PullRequest._from(self, latest).partial != partial):
            body = self.github.get_pull_request(self.root, latest.number).body
            new_body = wm.with_sections(body, sections or {})
            if partial is not None:
                new_body = wm.with_link_kind(new_body, task_branch.number, partial=partial)
            if new_body != body:
                self.github.edit_pull_request(self.root, latest.number, body=new_body)
        if latest.draft != draft:
            self.github.set_pull_request_draft(self.root, latest.number, draft)
        if (title and title != latest.title) or reviewers:
            self.github.edit_pull_request(self.root, latest.number, title=title or None, add_reviewers=reviewers)
        self.tracker.set_stage(task_branch.number, _board.IN_PROGRESS if draft else _board.IN_REVIEW)
        return wm.PullRequest._from(self, self.github.get_pull_request(self.root, latest.number))

    def _submit_branch(self, branch: wm.Branch, *, into: str, title: str | None,
                       draft: bool = False) -> wm.PullRequest:
        if branch.is_task_branch:
            raise WorkError(ErrorCode.PROTECTED_BRANCH, f"{branch.name} はタスクブランチです。",
                            hint=f"タスクブランチの反映は {self._op('task submit')} で行います。")
        if not self.is_admin() and (self.branch_creator(branch.name) or "").casefold() != self.access().login.casefold():
            self.require_admin(f"{branch.name} の提出（{branch.name} を作った人でないので）")
        self.git.fetch()
        for name in (branch.name, into):
            if not self.git.has_remote_branch(name):
                raise WorkError(ErrorCode.BRANCH_NOT_FOUND, f"GitHubにブランチ {name} がありません。")
        head, base = f"{_git.REMOTE}/{branch.name}", f"{_git.REMOTE}/{into}"
        # 取り込みのマージコミットだけ（ファイルの変更なし）でも反映しない（空のPRになる）。
        if self.git.count(f"{base}..{head}") == 0 or not self.git.has_changes(base, head):
            raise WorkError(ErrorCode.NOTHING_TO_SUBMIT, f"{branch.name} から {into} へ反映する変更がありません。")
        info = self.github.create_pull_request(
            self.root, head=branch.name, base=into, title=title or f"{branch.name} を {into} へ反映", body="",
            draft=draft,
        )
        return wm.PullRequest._from(self, info)

    def _merge_pull_request(self, number: int, *, ignore_checks: bool = False,
                            subject: str | None = None) -> wm.MergeResult:
        """PRをマージし、後処理（Issueを閉じる・ブランチを消す、途中の反映ならタスクブランチの作り直し）を行う。

        判断はすべて、ここで取得したGitHubの最新の内容で行う（呼び出し側が持つ古い PullRequest の値は使わない）。
        マージ済みのPRなら、途中で止まった後処理の残りだけを行う（もう一度実行すれば続きから終えられる）。
        """
        current = self.github.get_pull_request(self.root, number)
        pr = wm.PullRequest._from(self, current)
        if current.state == "merged":
            return self._finish_merge(pr, current, resumed=True)
        if current.state != "open":
            raise WorkError(ErrorCode.PULL_REQUEST_NOT_OPEN, f"PR #{pr.number} は開いていません（{current.state}）。")
        if current.draft:
            raise WorkError(ErrorCode.PULL_REQUEST_DRAFT, f"PR #{pr.number} は下書きです。",
                            hint=f"準備ができたら、タスクブランチで {self._op('task submit')} を実行して下書きを解除してください。")
        if not ignore_checks:
            checks = self.github.pull_request_activity(self.root, pr.number).checks
            results = [(c.name, _github.ci_result(c.status, c.conclusion)) for c in checks]
            failed = [name for name, result in results if result == _github.FAILED]
            if failed:
                raise WorkError(ErrorCode.CHECKS_FAILED, f"PR #{pr.number} のCIが失敗しています：{', '.join(failed)}",
                                hint=f"直してpushし、CIが通ってから実行してください（{self._op('task status')} で確認）。"
                                     "失敗を承知でマージする場合は --ignore-checks。")
            running = [name for name, result in results if result == _github.PENDING]
            if not checks and self._has_workflows():
                running = ["（まだ始まっていません。PRを出した直後など）"]
            if running:
                # 実行中のCI（ci rerun の直後等）を待たずにマージすると、失敗する変更が入りうる
                raise WorkError(ErrorCode.CHECKS_PENDING, f"PR #{pr.number} のCIが実行中です：{', '.join(running)}",
                                hint=f"結果を待ってから実行してください（{self._op('ci status')}）。"
                                     "待たずにマージする場合は --ignore-checks。")
        task = wm.task_number(pr.head)
        if task is not None and not pr.partial:
            # 最後のPRのマージはタスクの終了：子タスクが終わるまで親は終了できない（途中の反映はよい）
            self.tracker.check_finishable(task, action="最後のPRをマージ")
        try:
            if task is None:
                # ブランチ同士はマージコミットで履歴を残す。
                self.github.merge_pull_request(self.root, pr.number, squash=False, subject=None)
                return wm.MergeResult(pr.number, "merge", None, False)
            self.github.merge_pull_request(self.root, pr.number, squash=True,
                                           subject=f"{subject or pr.title} (#{pr.number})")
        except WorkError as error:
            if error.code == ErrorCode.PULL_REQUEST_CONFLICT:
                error.hint = (
                    f"タスクブランチ {pr.head} で {self._op('sync')} を実行して {pr.base} を取り込み、衝突を解決して、"
                    f"{self._op('task push')} してから、もう一度実行してください。" if task is not None else
                    f"{pr.base} の変更を {pr.head} へ取り込んで衝突を解決してから、もう一度実行してください。")
            raise
        return self._finish_merge(pr, current, resumed=False)

    def _finish_merge(self, pr: wm.PullRequest, info: _github.PullRequestInfo, *, resumed: bool) -> wm.MergeResult:
        """マージした後の処理。今の状態を見て、終わっていない手順だけを行う（何度呼んでもよい）。"""
        task = wm.task_number(pr.head)
        method = "merge" if task is None else "squash"
        done = WorkError(ErrorCode.PULL_REQUEST_NOT_OPEN, f"PR #{pr.number} は既にマージ済みです（後処理も済んでいます）。")
        if task is None:
            if resumed:
                raise done  # ブランチ同士のPRには後処理がない
            return wm.MergeResult(pr.number, method, None, False)
        try:
            self.git.fetch()
            if pr.partial:
                if resumed and not self._needs_rebuild(pr.head, info.head_sha):
                    raise done
                rebuilt = self._rebuild_task_branch(pr.head, info.head_sha)
                self.tracker.set_stage(task, _board.IN_PROGRESS)  # 途中の反映：作業は続く
                return wm.MergeResult(pr.number, method, None, rebuilt, resumed)
            issue_open = self.github.get_issue(self.root, task).state == "open"
            # 消すのは、マージしたときのままのブランチだけ（後からpushされたコミットを失わないように）
            stale_branch = (self.git.has_remote_branch(pr.head) and info.head_sha is not None
                            and self.git.rev_parse(f"{_git.REMOTE}/{pr.head}") == info.head_sha)
            if resumed and not (issue_open or stale_branch):
                raise done
            if issue_open:
                self.github.close_issue(self.root, task)
            if stale_branch:
                self.git.push_delete(pr.head)
            self.tracker.closed(task)
            return wm.MergeResult(pr.number, method, task, False, resumed)
        except WorkError as error:
            if error is not done:
                error.hint = ((error.hint + "\n") if error.hint else "") + (
                    f"取り込みは済んでいます。もう一度 {self._op('task finish')} {task} を実行すると、"
                    "残りの後処理（Issueを閉じる・ブランチを消す・タスクブランチの作り直し・片付け）だけを行います。")
            raise

    def _needs_rebuild(self, branch: str, merged_head: str | None) -> bool:
        """途中の反映をマージした後、タスクブランチをまだ作り直していないか（マージした版を含んだままか）。"""
        return (merged_head is not None and self.git.has_local_branch(branch)
                and self.git.rev_parse(merged_head) is not None and self.git.is_ancestor(merged_head, branch))

    def _rebuild_task_branch(self, branch: str, merged_head: str | None) -> bool:
        """--partialのPRをsquashマージした後、タスクブランチを作成元の最新から作り直す。

        PRに含まれなかった続きのコミットは載せ替える（git rebase --onto と同じ）。
        """
        if not self._needs_rebuild(branch, merged_head):
            return False
        base = self.git.get_config(wm.base_key(branch)) or self.default_base
        previous = self.git.current_branch()
        if previous != branch:
            self._guard_switch("タスクブランチの作り直し（一時的に切り替わる）")
        outcome = self.git.rebase_onto(f"{_git.REMOTE}/{base}", merged_head, branch)
        if not outcome.merged:
            raise WorkError(
                ErrorCode.MERGE_CONFLICT,
                "タスクブランチの作り直しで衝突しました。",
                hint=f"ファイルを直して {self._op('sync continue')} で続けてください"
                     f"（やめる場合は {self._op('sync abort')}）。",
                details=list(outcome.conflicted),
            )
        self.git.push(branch, force=True)
        if previous is not None and previous != branch:
            self.git.switch(previous)  # rebaseで移ったタスクブランチから、元のブランチへ戻る
        return True

    def _check_usable(self, ref: str, name: str) -> None:
        """手元を ref（ブランチ name）の内容にできなければ止める（Hooks.unusable）。"""
        reason = self.hooks.unusable(self, [ref]).get(ref)
        if reason is not None:
            raise WorkError(ErrorCode.INVALID_BASE, f"{name} には切り替えられません（{reason}）。",
                            hint="作成元には、使えるブランチ（branch list）を指定してください。")

    def _branch(self, name: str, local: bool, remote: bool) -> wm.Branch:
        is_task_branch = wm.is_task_branch(name)
        base = self.git.get_config(wm.base_key(name)) if is_task_branch else None
        return wm.Branch(name, is_task_branch, base, local, remote, self)

    def _existing_task_branch(self, number: int) -> str | None:
        """タスクのタスクブランチで、手元かGitHub（取得済みの写し）にあるものの名前。なければNone。"""
        for names in (self.git.local_branches(), self.git.remote_branches()):
            found = [name for name in names if wm.task_number(name) == number]
            if found:
                return found[0]
        return None

    def _task_branch_of(self, number: int) -> str:
        """タスクのタスクブランチの名前（task/<番号>-<名前>）。手元・GitHub・Issueの記録の順に探す。

        どこにもなければ（名前を付ける前に作り、もう消したもの等）task/<番号>。"""
        return (self._existing_task_branch(number) or wm.issue_branch(self.github.get_issue(self.root, number).body)
                or wm.task_branch_name(number))

    def _parent_task_branch(self, number: int) -> str | None:
        """子タスクの作成元にする、親タスクのタスクブランチ（親が開いていれば task/<親>-<名前>）。親がなければNone。

        親のタスクブランチがまだなければ、作るときの名前（記録したもの、なければ親の題名から）。"""
        parent = self.github.issue_relation(self.root, number).parent
        if parent is None:
            return None
        info = self.github.get_issue(self.root, parent)
        if info.state != "open":
            return None
        return (self._existing_task_branch(parent) or wm.issue_branch(info.body)
                or wm.task_branch_name(parent, wm.branch_label(info.title) or None))

    def _child_base(self, number: int, base: str | None, parent_branch: str | None) -> str | None:
        """新しいタスクブランチの作成元。子タスクなら親のタスクブランチ（GitHubになければ作る）で、他は指定できない。"""
        if parent_branch is None:
            return base
        if base is not None and base != parent_branch:
            raise WorkError(ErrorCode.INVALID_BASE,
                            f"#{number} は子タスクなので、作成元は親のタスクブランチ {parent_branch} です（{base} は指定できません）。",
                            hint=f"親子をやめるなら {self._op('task edit')} {number} --clear-parent。")
        self._ensure_task_branch(parent_branch)
        return parent_branch

    def _ensure_task_branch(self, branch: str) -> None:
        """タスクのタスクブランチのブランチがGitHubになければ作る（手元には作らない）。親の親も同じ。

        子タスクを始めるとき、まだ始めていない親のタスクブランチを用意するために使う。作成元は、親があれば親のタスクブランチ、
        なければIssueに記録したもの（なければ default_base）。
        """
        number = wm.task_number(branch)
        if self.git.has_remote_branch(branch):
            return
        parent_branch = self._parent_task_branch(number)
        recorded = wm.issue_base(self.github.get_issue(self.root, number).body)
        base = self._child_base(number, None, parent_branch) or recorded or self.default_base
        self.git.run("push", "--quiet", _git.REMOTE,
                     f"{self._base_start_point(base, task_branch=parent_branch)}:refs/heads/{branch}")
        self.git.fetch()
        self._record_base(number, base, branch=branch)
        self.notices.append(f"親タスク #{number} のタスクブランチ {branch} をGitHubに作りました（作成元 {base}）。"
                            f"親の作業は {self._op('task start')} {number} で始められます。")

    def _base_start_point(self, base: str | None, *, task_branch: str | None = None) -> str:
        """作成元のブランチを確かめ、GitHubの最新を起点として返す。

        タスクブランチは作成元にできない。ただし task_branch（子タスクにとっての親のタスクブランチ）は作成元にできる。
        """
        base = base or self.default_base
        if wm.is_task_branch(base) and base != task_branch:
            raise WorkError(
                ErrorCode.INVALID_BASE,
                f"タスクブランチ {base} は作成元にできません。",
                hint="タスクブランチでないブランチ（main・develop等）を指定してください。",
            )
        self.git.fetch()
        if self.git.has_remote_branch(base):
            return f"{_git.REMOTE}/{base}"
        if self.git.has_local_branch(base):
            return base
        raise WorkError(ErrorCode.BRANCH_NOT_FOUND, f"作成元のブランチ {base} がありません。")

    def _delete_branch(self, branch: wm.Branch, *, dry_run: bool = False) -> None:
        if branch.is_task_branch:
            raise WorkError(ErrorCode.PROTECTED_BRANCH, f"{branch.name} はタスクブランチです。",
                            hint=f"タスクブランチは {self._op('task prune')} で片付けます。")
        protected = {self.default_base, self.github.default_branch(self.root)}
        if branch.name in protected:
            raise WorkError(ErrorCode.PROTECTED_BRANCH, f"{branch.name} は既定のブランチなので消せません。")
        self.require_admin("ブランチの削除")
        users = [name for name in self.git.local_branches()
                 if wm.is_task_branch(name) and self.git.get_config(wm.base_key(name)) == branch.name]
        if users:
            raise WorkError(ErrorCode.PROTECTED_BRANCH,
                            f"{branch.name} はタスクブランチ（{', '.join(users)}）の作成元なので消せません。",
                            hint=f"先にタスクブランチを片付けてください（{self._op('task prune')}）。")
        if self.git.current_branch() == branch.name:
            raise WorkError(ErrorCode.PROTECTED_BRANCH, f"今いるブランチ {branch.name} は消せません。",
                            hint="別のブランチへ移ってから実行してください。")
        if dry_run:
            return
        if branch.local:
            self.git.delete_branch(branch.name, force=True)
        if branch.remote:
            self.git.push_delete(branch.name)

    def _start_task_branch(self, task: wm.Task, base: str | None, *, name: str | None = None,
                           ignore_blocked: bool = False, take_over: bool = False) -> wm.TaskBranch:
        if task.state != "open":
            raise WorkError(ErrorCode.TASK_CLOSED, f"Issue #{task.number} は閉じています。",
                            hint="作業を再開するには、GitHubでIssueを開き直してください。")
        if self._dirty():
            raise WorkError(
                ErrorCode.DIRTY_WORKING_TREE,
                "未コミットの変更があるため、タスクブランチを作れません（別のIssueの作業に混ざるのを防ぐため）。",
                hint=f"変更をコミットするか、{self._op('stash')} で退避してから実行してください。",
            )
        if self.git.current_branch() != self._existing_task_branch(task.number):   # 同じタスクブランチなら切り替わらない
            self._guard_switch("タスクブランチを切り替え")
        self.tracker.check_assignee(task.number, take_over=take_over)   # 他の人の作業に重ねない
        self.install_hooks()  # 前からあるcloneにも、作業を始めるときに入れる
        self.git.fetch()
        self._tidy_finished()
        if name:
            name = wm.check_branch_label(name)   # 作業を始める前に確かめる（既にあるタスクブランチなら使わない）
        branch = self._existing_task_branch(task.number)
        if branch is not None and self.git.has_local_branch(branch):
            self._check_usable(branch, branch)
            # 既にあるタスクブランチへ戻る。別の場所でpushされた続きがあれば早送りで取り込む
            # （手元にだけのコミットもあって早送りできないときは、sync で取り込む）。
            self.git.switch(branch)
            self.git.fetch()
            remote = f"{_git.REMOTE}/{branch}"
            if self.git.has_remote_branch(branch) and self.git.is_ancestor(branch, remote):
                self.git.merge(remote, ff_only=True)
            # 子タスクの作業で作られた親のタスクブランチなど、担当者を決めずにできたタスクブランチもあるので、ここでも担当者にする
            if not task.assignees:
                self.github.edit_issue(self.root, task.number, add_assignees=("@me",))
        else:
            # 手元にないタスクブランチ：GitHubにあればそこから再開し、作成元も記録したものにする。
            self.git.fetch()
            remote = branch is not None and self.git.has_remote_branch(branch)
            if not remote and not name:
                # 前に作って消したタスクブランチなら、Issueに記録した名前で作り直す
                recorded = wm.issue_branch(self.github.get_issue(self.root, task.number).body) or ""
                prefix = wm.task_branch_name(task.number) + "-"
                if recorded.startswith(prefix):
                    name = recorded.removeprefix(prefix)
            if not remote:
                self.tracker.check_startable(task.number, ignore_blocked=ignore_blocked)
                if name == "":
                    suggestion = wm.branch_label(task.title) or "<名前>"
                    raise WorkError(ErrorCode.BRANCH_NAME_REQUIRED,
                                    f"新しいタスクブランチの名前を指定してください（task/{task.number}-<名前>）。",
                                    hint=f"{self._op('task start')} {task.number} --name {suggestion}"
                                         "（題名から作った例。日本語も使えます）")
                branch = wm.task_branch_name(task.number, name)
            if base is None and remote:
                base = self._recorded_base(task.number, branch)
            parent_branch = self._parent_task_branch(task.number)
            if not remote:
                base = self._child_base(task.number, base, parent_branch)
            start = self._base_start_point(base, task_branch=parent_branch)
            if remote:
                start = f"{_git.REMOTE}/{branch}"
            base = base or self.default_base
            self._check_usable(start, branch if remote else base)
            self.git.create_branch(branch, start, switch=False)
            if remote:
                self.git.set_upstream(branch)
            else:
                # 新しいタスクブランチは、作った時点でGitHubにも置く（本体はGitHub、手元はその写し）。
                try:
                    self.git.push(branch, set_upstream=True)
                except WorkError:
                    self.git.delete_branch(branch, force=True)
                    raise
            self.git.switch(branch)
            self.git.set_config(wm.base_key(branch), base)
            self._record_base(task.number, base, claim=True, branch=branch)
            if not remote:
                self.tracker.set_stage(task.number, _board.IN_PROGRESS)
        task_branch = self.current_task_branch()
        assert task_branch is not None
        self.hooks.after_switch(self)
        return task_branch

    def __repr__(self) -> str:
        return f"Repository({str(self.root)!r})"


def _quiet(message: str) -> None:
    pass


def _remove_tree(path: Path) -> None:
    """gitの読み取り専用ファイル（Windows）も含めて削除する。"""
    def retry(function, target, _):
        os.chmod(target, stat.S_IWRITE)
        function(target)
    shutil.rmtree(path, onerror=retry)
