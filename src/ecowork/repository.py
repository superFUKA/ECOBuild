"""リポジトリ：作業の対象（GitHubのリポジトリ＋手元のclone）と、作業の進め方。

作業空間＝Issue＝task/<番号> のブランチ。コミットは作業空間でだけ行い、
作業空間でないブランチ（main・develop等）への変更はPRのマージでだけ入る。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from . import git as _git
from . import github as _github
from . import workspace as ws
from .errors import ErrorCode, WorkError, operation


class Hooks:
    """作業の流れの途中に、利用側の処理を入れる口。既定は何もしない。"""

    def after_sync(self, repository: "Repository") -> object:
        """sync・sync continue で取り込みが終わった後（衝突で止まったときは呼ばない）。

        戻り値は SyncResult.extra に入る。
        """
        return None

    def before_submit(self, repository: "Repository") -> None:
        """作業空間の反映（submit）で、pushする前。止めるときは WorkError を投げる。"""


class Repository:
    def __init__(
        self,
        root: Path | str,
        *,
        github: _github.GitHub | None = None,
        default_base: str = "main",
        command: str = "",
        hooks: Hooks | None = None,
    ):
        """
        default_base：作成元を省略したときのブランチ。
        command：ヒントに書くCLIのコマンド名（errors.operation）。
        github：試験でGitHubへの接続を差し替えるためのもの。
        """
        self.root = Path(root)
        self.default_base = default_base
        self.command = command
        self.hooks = hooks if hooks is not None else Hooks()
        self.github = github if github is not None else _github.default()
        self.git = _git.Git(self.root, command=command)

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
    ) -> "Repository":
        """GitHubリポジトリを作ってcloneし、populateで用意したファイルを初回コミットとしてpushする。"""
        root = Path(directory).resolve() / name
        if root.exists():
            raise WorkError(ErrorCode.ALREADY_EXISTS, f"{root} は既に存在します。")
        github = github if github is not None else _github.default()
        repository = github.create_repository(name, owner=owner, private=private, description=description)
        try:
            repo = _git.clone(repository.clone_url, root)
            repo.run("symbolic-ref", "HEAD", f"refs/heads/{default_base}")
            if populate is not None:
                populate(root)
            repo.add(all=True)
            repo.commit(message, allow_empty=populate is None)
            repo.push(default_base, set_upstream=True)
        except WorkError as error:
            error.hint = (error.hint + "\n" if error.hint else "") + (
                f"GitHubのリポジトリ {repository.full_name} は作成済みです。"
                f"やり直す場合は、リポジトリと {root} を削除してから実行してください。"
            )
            raise
        return cls(root, github=github, default_base=default_base, command=command, hooks=hooks)

    @property
    def remote_url(self) -> str | None:
        return self.git.get_config("remote.origin.url")

    # 状態 -----------------------------------------------------------------

    def status(self) -> ws.Status:
        tree = self.git.working_tree()
        workspace = self.current_workspace()
        pull_request = None
        if workspace is not None:
            pulls = self.github.pull_requests_for_branch(self.root, workspace.branch)
            if pulls:
                latest = max(pulls, key=lambda p: p.number)
                pull_request = ws.PullRequestState(latest.number, latest.url, latest.state)
        return ws.Status(
            branch=tree.branch,
            workspace=None if workspace is None else workspace.number,
            base=None if workspace is None else workspace.base,
            staged=tree.staged, unstaged=tree.unstaged, untracked=tree.untracked, conflicted=tree.conflicted,
            ahead=tree.ahead, behind=tree.behind, merging=self.git.is_merging(), pull_request=pull_request,
            upstream_gone=tree.upstream_gone,
        )

    # ブランチ ---------------------------------------------------------------

    def branches(self) -> list[ws.Branch]:
        self.git.fetch()
        local = set(self.git.local_branches())
        remote = set(self.git.remote_branches())
        return [self._branch(name, name in local, name in remote) for name in sorted(local | remote)]

    def branch(self, name: str) -> ws.Branch:
        self.git.fetch()
        local, remote = self.git.has_local_branch(name), self.git.has_remote_branch(name)
        if not (local or remote):
            raise WorkError(ErrorCode.BRANCH_NOT_FOUND, f"ブランチ {name} がありません。")
        return self._branch(name, local, remote)

    def create_branch(self, name: str, *, base: str | None = None) -> ws.Branch:
        """作業空間でないブランチを作り、GitHubへ反映する。"""
        if ws.is_workspace_branch(name):
            raise WorkError(
                ErrorCode.RESERVED_BRANCH_NAME,
                f"{ws.WORKSPACE_PREFIX} で始まる名前は作業空間専用です。",
                hint=f"作業空間は {self._op('task start')} <Issue番号> で作ります。",
            )
        start = self._base_start_point(base)
        if self.git.has_local_branch(name) or self.git.has_remote_branch(name):
            raise WorkError(ErrorCode.ALREADY_EXISTS, f"ブランチ {name} は既にあります。")
        self.git.create_branch(name, start, switch=False)
        self.git.push(name, set_upstream=True)
        return self._branch(name, True, True)

    # タスクと作業空間 ---------------------------------------------------------

    def create_task(self, title: str, *, body: str = "") -> ws.Task:
        return ws.Task._from(self, self.github.create_issue(self.root, title, body))

    def task(self, number: int) -> ws.Task:
        return ws.Task._from(self, self.github.get_issue(self.root, number))

    def current_workspace(self) -> ws.Workspace | None:
        branch = self.git.current_branch()
        number = None if branch is None else ws.workspace_number(branch)
        if number is None:
            return None
        base = self.git.get_config(ws.base_key(branch)) or self.default_base
        return ws.Workspace(number, branch, base, self)

    def require_workspace(self, action: str) -> ws.Workspace:
        workspace = self.current_workspace()
        if workspace is None:
            raise WorkError(
                ErrorCode.NOT_IN_WORKSPACE,
                f"{action}は作業空間（task/<番号>のブランチ）でだけ行えます。",
                hint=f"{self._op('task start')} <Issue番号> で作業空間を作るか、作業空間へ切り替えてください。",
            )
        return workspace

    def pull_request(self, number: int | None = None) -> ws.PullRequest:
        """PRを返す。番号を省略すると、今の作業空間の開いているPR。"""
        if number is not None:
            return ws.PullRequest._from(self, self.github.get_pull_request(self.root, number))
        workspace = self.require_workspace("番号を省略したPRの指定")
        pulls = [p for p in self.github.pull_requests_for_branch(self.root, workspace.branch) if p.state == "open"]
        if not pulls:
            raise WorkError(ErrorCode.NO_PULL_REQUEST, f"{workspace.branch} の開いているPRがありません。",
                            hint=f"{self._op('task submit')} でPRを作成してください。")
        return ws.PullRequest._from(self, max(pulls, key=lambda p: p.number))

    def clean_workspaces(self, *, dry_run: bool = False) -> ws.CleanResult:
        """Issueが閉じた作業空間のブランチを片付ける。未pushの変更がある作業空間は残す。"""
        self.git.fetch()
        current = self.git.current_branch()
        removed, skipped, switched_to = [], [], None
        for branch in self.git.local_branches():
            number = ws.workspace_number(branch)
            if number is None:
                continue
            try:
                issue = self.github.get_issue(self.root, number)
            except WorkError:
                skipped.append(ws.SkippedWorkspace(branch, "Issueを取得できません"))
                continue
            if issue.state != "closed":
                continue
            reason = self._unsafe_to_remove(branch)
            if reason is not None:
                skipped.append(ws.SkippedWorkspace(branch, reason))
                continue
            if dry_run:
                removed.append(branch)
                continue
            if branch == current:
                if not self.git.working_tree().clean:
                    skipped.append(ws.SkippedWorkspace(branch, "今いる作業空間に未コミットの変更があります"))
                    continue
                switched_to = self.git.get_config(ws.base_key(branch)) or self.default_base
                self._switch_to_latest(switched_to)
            self.git.delete_branch(branch, force=True)
            if self.git.has_remote_branch(branch):
                self.git.push_delete(branch)
            self.git.unset_config(ws.base_key(branch))
            removed.append(branch)
        return ws.CleanResult(tuple(removed), tuple(skipped), switched_to, dry_run)

    def drop_workspace(self, number: int | None = None, *, close: bool = False, discard: bool = False,
                       dry_run: bool = False) -> ws.DropResult:
        """PRを出さずに作業をやめる：開いているPRを閉じ、作業空間を手元とGitHubから消す。

        numberを省略すると今いる作業空間。今いる作業空間なら作成元へ移って最新にする。
        Issueは既定で開いたまま（後で task start で最初からやり直せる）。closeで「対応しない」として閉じる。
        作成元に入っていないコミットは失われるため、discardがなければ止める。
        dry_runは何もせず、行う内容（失われるコミット等）を返す。
        """
        if number is None:
            workspace = self.require_workspace("作業の中断")
            number, branch = workspace.number, workspace.branch
        else:
            branch = ws.workspace_branch(number)
        current = self.git.current_branch()
        if current == branch and not self.git.working_tree().clean:
            raise WorkError(
                ErrorCode.DIRTY_WORKING_TREE,
                "未コミットの変更があるため、作業空間を捨てられません。",
                hint=f"残す変更は {self._op('commit')} か {self._op('stash')}、"
                     f"捨てる変更は {self._op('restore')} で片付けてから実行してください。",
            )
        self.git.fetch()
        local, remote = self.git.has_local_branch(branch), self.git.has_remote_branch(branch)
        if not (local or remote):
            if close:
                # 開始していない（作業空間のない）Issueを「対応しない」として閉じる。
                if not dry_run and self.github.get_issue(self.root, number).state == "open":
                    self.github.close_issue(self.root, number, not_planned=True)
                return ws.DropResult(number, branch, (), (), None, close, dry_run)
            raise WorkError(ErrorCode.BRANCH_NOT_FOUND, f"作業空間 {branch} がありません。",
                            hint="開始していないIssueをやめる場合は --close を付けてください（「対応しない」として閉じます）。")
        base = self.git.get_config(ws.base_key(branch)) or self.default_base
        lost = self._lost_commits(branch, base, local=local, remote=remote)
        pulls = tuple(p.number for p in self.github.pull_requests_for_branch(self.root, branch) if p.state == "open")
        switched_to = base if current == branch else None
        if dry_run:
            return ws.DropResult(number, branch, lost, pulls, switched_to, close, True)
        if lost and not discard:
            raise WorkError(
                ErrorCode.COMMITS_WOULD_BE_LOST,
                f"{branch} には {base} に入っていないコミットが {len(lost)} 件あり、捨てると失われます。",
                hint="捨ててよいか確認してから実行してください。",
                details=list(lost),
            )
        for pull in pulls:
            self.github.close_pull_request(self.root, pull)
        if switched_to is not None:
            self._switch_to_latest(switched_to)
        if local:
            self.git.delete_branch(branch, force=True)
        if remote:
            self.git.push_delete(branch)
        self.git.unset_config(ws.base_key(branch))
        if close and self.github.get_issue(self.root, number).state == "open":
            self.github.close_issue(self.root, number, not_planned=True)
        return ws.DropResult(number, branch, lost, pulls, switched_to, close, False)

    # 最新化・退避・取り消し ------------------------------------------------------

    def sync(self) -> ws.SyncResult:
        """GitHubの最新を取り込む。作業空間でないブランチは早送り、作業空間は作成元の最新も取り込む。"""
        if self.git.is_merging() or self.git.is_rebasing():
            raise self._in_progress_error()
        branch = self.git.current_branch()
        if branch is None:
            raise WorkError(ErrorCode.GIT_ERROR, "ブランチにいません（切り離された状態です）。")
        workspace = self.current_workspace()
        if workspace is not None and self.github.get_issue(self.root, workspace.number).state != "open":
            # 反映済みの作業空間へ作成元を取り込むと、squashマージのため衝突や余分なコミットになる。
            raise WorkError(
                ErrorCode.TASK_CLOSED,
                f"Issue #{workspace.number} は閉じているため、作業空間 {workspace.branch} は取り込みの対象外です。",
                hint=f"{self._op('task clean')} で片付けて {workspace.base} へ移ってください。"
                     "続きの作業は新しいIssueで行います。",
            )
        self.git.fetch()
        merged = []
        refs = [f"{_git.REMOTE}/{branch}"]
        if workspace is not None:
            refs.append(f"{_git.REMOTE}/{workspace.base}")
        for ref in refs:
            if self.git.rev_parse(ref) is None:
                continue
            # 作業空間でないブランチは早送りだけ（コミットはPRのマージでだけ入る）。
            outcome = self.git.merge(ref, ff_only=workspace is None,
                                     message=None if workspace is None else f"{ref} を取り込み")
            if not outcome.merged:
                raise WorkError(
                    ErrorCode.MERGE_CONFLICT,
                    f"{ref} の取り込みで衝突しました。",
                    hint=f"衝突したファイルを直して {self._op('add')} で登録し、{self._op('sync continue')}"
                         f"（または {self._op('commit')}）で完了してください。やめる場合は {self._op('sync abort')}。",
                    details=list(outcome.conflicted),
                )
            if not outcome.already_up_to_date:
                merged.append(ref)
        return ws.SyncResult(branch, tuple(merged), self.hooks.after_sync(self))

    def continue_sync(self) -> ws.SyncResult:
        """衝突を解決した後、止まっている取り込み（または作業空間の作り直し）を完了する。"""
        branch = self.git.current_branch() or ""
        if self.git.is_rebasing() or self.git.is_merging():
            self._refuse_conflict_markers(self.git.conflict_markers(cached=True))
        if self.git.is_rebasing():
            outcome = self.git.rebase_continue()
            if not outcome.merged:
                raise WorkError(ErrorCode.MERGE_CONFLICT, "続きの載せ替えで衝突しました。",
                                hint=f"ファイルを直して {self._op('add')} で登録し、"
                                     f"もう一度 {self._op('sync continue')}。",
                                details=list(outcome.conflicted))
            branch = self.git.current_branch() or branch
            return ws.SyncResult(branch, ("rebase",), self.hooks.after_sync(self))
        if self.git.is_merging():
            self.git.merge_continue()
            return ws.SyncResult(branch, ("merge",), self.hooks.after_sync(self))
        raise WorkError(ErrorCode.NO_SYNC_IN_PROGRESS, "止まっている取り込みはありません。")

    def abort_sync(self) -> None:
        if self.git.is_rebasing():
            self.git.rebase_abort()
        elif self.git.is_merging():
            self.git.merge_abort()
        else:
            raise WorkError(ErrorCode.NO_SYNC_IN_PROGRESS, "止まっている取り込みはありません。")

    def stash(self) -> ws.StashResult:
        stashed = self.git.stash_push()
        return ws.StashResult(stashed, self._stash_messages())

    def stash_pop(self) -> ws.StashResult:
        if not self.git.stash_list():
            raise WorkError(ErrorCode.NO_SYNC_IN_PROGRESS, "退避した変更はありません。")
        outcome = self.git.stash_pop()
        if not outcome.merged:
            # 作業空間でないブランチでは add できない。登録を外せば（restore --staged）解決済みになる。
            mark = (f"{self._op('add')} で登録" if self.current_workspace() is not None
                    else f"{self._op('restore')} --staged <パス> で解決済みに")
            raise WorkError(ErrorCode.MERGE_CONFLICT, "退避した変更を戻すときに衝突しました。",
                            hint=f"衝突したファイルを直して {mark}してください。退避した変更は残っているので、"
                                 f"解決したら {self._op('stash drop')} で捨ててください。",
                            details=list(outcome.conflicted))
        return ws.StashResult(True, self._stash_messages())

    def stash_drop(self) -> ws.StashResult:
        if not self.git.stash_list():
            raise WorkError(ErrorCode.NO_SYNC_IN_PROGRESS, "退避した変更はありません。")
        self.git.run("stash", "drop", "--quiet")
        return ws.StashResult(False, self._stash_messages())

    def stashes(self) -> tuple[str, ...]:
        return self._stash_messages()

    def restore(self, *paths: str, staged: bool = False) -> ws.RestoreResult:
        self.git.restore(paths, staged=staged)
        return ws.RestoreResult(paths, staged)

    # 内部 -----------------------------------------------------------------

    def _op(self, name: str) -> str:
        return operation(self.command, name)

    def _stash_messages(self) -> tuple[str, ...]:
        return tuple(entry.message for entry in self.git.stash_list())

    def _in_progress_error(self) -> WorkError:
        return WorkError(
            ErrorCode.MERGE_CONFLICT,
            "前回の取り込みが衝突で止まっています。",
            hint=f"ファイルを直して {self._op('add')} で登録し、{self._op('sync continue')} で続けるか、"
                 f"{self._op('sync abort')} でやめてください。",
            details=list(self.git.working_tree().conflicted),
        )

    def _refuse_conflict_markers(self, markers: tuple[str, ...], *, committed: bool = False) -> None:
        """衝突の印が残っていれば止める（gitは印が残ったままでも登録・コミットできてしまう）。"""
        if not markers:
            return
        then = (f"{self._op('commit')} でコミットしてから、もう一度実行してください" if committed
                else f"{self._op('add')} で登録してから、もう一度実行してください")
        raise WorkError(
            ErrorCode.CONFLICT_MARKERS,
            f"衝突の印（<<<<<<< 等）が残っています（{len(markers)} か所）。",
            hint=f"印の場所を直して {then}。",
            details=list(markers),
        )

    def _unsafe_to_remove(self, branch: str) -> str | None:
        """消すと失われるコミットがあれば理由を返す。"""
        tip = self.git.rev_parse(branch)
        if self.git.has_remote_branch(branch) and self.git.is_ancestor(tip, f"{_git.REMOTE}/{branch}"):
            return None
        if any(self.git.is_ancestor(tip, sha) for sha in self._merged_heads(branch)):
            return None
        return "GitHubにないコミットがあります"

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
        """作業空間を消すと失われるコミット（作成元にも、マージ済みのPRにも入っていないもの）の件名。"""
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

    def _submit_workspace(self, workspace: ws.Workspace, *, title: str | None, partial: bool) -> ws.PullRequest:
        self.hooks.before_submit(self)
        self.git.fetch()
        base_ref = f"{_git.REMOTE}/{workspace.base}"
        if (self.git.count(f"{base_ref}..{workspace.branch}") == 0
                or not self.git.has_changes(base_ref, workspace.branch)):
            raise WorkError(ErrorCode.NOTHING_TO_SUBMIT, f"{workspace.base} へ反映する変更がありません。",
                            hint="変更をコミットしてから再実行してください。")
        self._refuse_conflict_markers(self.git.conflict_markers(f"{base_ref}...{workspace.branch}"), committed=True)
        workspace.push()
        opened = [p for p in self.github.pull_requests_for_branch(self.root, workspace.branch) if p.state == "open"]
        if opened:
            # 既にあるPRには、pushしたコミットがそのまま加わる。
            return ws.PullRequest._from(self, max(opened, key=lambda p: p.number))
        issue = self.github.get_issue(self.root, workspace.number)
        keyword = "Refs" if partial else "Closes"
        info = self.github.create_pull_request(
            self.root, head=workspace.branch, base=workspace.base,
            title=title or issue.title, body=f"{keyword} #{workspace.number}\n",
        )
        return ws.PullRequest._from(self, info)

    def _submit_branch(self, branch: ws.Branch, *, into: str, title: str | None) -> ws.PullRequest:
        if branch.is_workspace:
            raise WorkError(ErrorCode.PROTECTED_BRANCH, f"{branch.name} は作業空間です。",
                            hint=f"作業空間の反映は {self._op('task submit')} で行います。")
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
        )
        return ws.PullRequest._from(self, info)

    def _merge_pull_request(self, pr: ws.PullRequest) -> ws.MergeResult:
        current = self.github.get_pull_request(self.root, pr.number)
        if current.state != "open":
            raise WorkError(ErrorCode.PULL_REQUEST_NOT_OPEN, f"PR #{pr.number} は開いていません（{current.state}）。")
        number = ws.workspace_number(pr.head)
        try:
            if number is None:
                # ブランチ同士はマージコミットで履歴を残す。
                self.github.merge_pull_request(self.root, pr.number, squash=False, subject=None)
                return ws.MergeResult(pr.number, "merge", None, False)
            self.github.merge_pull_request(self.root, pr.number, squash=True,
                                           subject=f"{pr.title} (#{pr.number})")
        except WorkError as error:
            if error.code == ErrorCode.PULL_REQUEST_CONFLICT:
                error.hint = (
                    f"作業空間 {pr.head} で {self._op('sync')} を実行して {pr.base} を取り込み、衝突を解決して、"
                    f"{self._op('push')} してから、もう一度実行してください。" if number is not None else
                    f"{pr.base} の変更を {pr.head} へ取り込んで衝突を解決してから、もう一度実行してください。")
            raise
        if pr.partial:
            rebuilt = self._rebuild_workspace(pr.head, current.head_sha)
            return ws.MergeResult(pr.number, "squash", None, rebuilt)
        if self.github.get_issue(self.root, number).state == "open":
            self.github.close_issue(self.root, number)
        self.git.fetch()
        if self.git.has_remote_branch(pr.head):
            self.git.push_delete(pr.head)
        return ws.MergeResult(pr.number, "squash", number, False)

    def _rebuild_workspace(self, branch: str, merged_head: str | None) -> bool:
        """--partialのPRをsquashマージした後、作業空間を作成元の最新から作り直す。

        PRに含まれなかった続きのコミットは載せ替える（git rebase --onto と同じ）。
        """
        if merged_head is None or not self.git.has_local_branch(branch):
            return False
        self.git.fetch()
        base = self.git.get_config(ws.base_key(branch)) or self.default_base
        previous = self.git.current_branch()
        outcome = self.git.rebase_onto(f"{_git.REMOTE}/{base}", merged_head, branch)
        if not outcome.merged:
            raise WorkError(
                ErrorCode.MERGE_CONFLICT,
                "作業空間の作り直しで衝突しました。",
                hint=f"ファイルを直して {self._op('add')} で登録し、{self._op('sync continue')} で続けてください"
                     f"（やめる場合は {self._op('sync abort')}）。",
                details=list(outcome.conflicted),
            )
        self.git.push(branch, force=True)
        if previous is not None and previous != branch:
            self.git.switch(previous)  # rebaseで移った作業空間から、元のブランチへ戻る
        return True

    def _branch(self, name: str, local: bool, remote: bool) -> ws.Branch:
        is_workspace = ws.is_workspace_branch(name)
        base = self.git.get_config(ws.base_key(name)) if is_workspace else None
        return ws.Branch(name, is_workspace, base, local, remote, self)

    def _base_start_point(self, base: str | None) -> str:
        """作成元のブランチを確かめ、GitHubの最新を起点として返す。"""
        base = base or self.default_base
        if ws.is_workspace_branch(base):
            raise WorkError(
                ErrorCode.INVALID_BASE,
                f"作業空間 {base} は作成元にできません。",
                hint="作業空間でないブランチ（main・develop等）を指定してください。",
            )
        self.git.fetch()
        if self.git.has_remote_branch(base):
            return f"{_git.REMOTE}/{base}"
        if self.git.has_local_branch(base):
            return base
        raise WorkError(ErrorCode.BRANCH_NOT_FOUND, f"作成元のブランチ {base} がありません。")

    def _delete_branch(self, branch: ws.Branch, *, dry_run: bool = False) -> None:
        if branch.is_workspace:
            raise WorkError(ErrorCode.PROTECTED_BRANCH, f"{branch.name} は作業空間です。",
                            hint=f"作業空間は {self._op('task clean')} で片付けます。")
        protected = {self.default_base, self.github.default_branch(self.root)}
        if branch.name in protected:
            raise WorkError(ErrorCode.PROTECTED_BRANCH, f"{branch.name} は既定のブランチなので消せません。")
        users = [name for name in self.git.local_branches()
                 if ws.is_workspace_branch(name) and self.git.get_config(ws.base_key(name)) == branch.name]
        if users:
            raise WorkError(ErrorCode.PROTECTED_BRANCH,
                            f"{branch.name} は作業空間（{', '.join(users)}）の作成元なので消せません。",
                            hint=f"先に作業空間を片付けてください（{self._op('task clean')}）。")
        if self.git.current_branch() == branch.name:
            raise WorkError(ErrorCode.PROTECTED_BRANCH, f"今いるブランチ {branch.name} は消せません。",
                            hint="別のブランチへ移ってから実行してください。")
        if dry_run:
            return
        if branch.local:
            self.git.delete_branch(branch.name, force=True)
        if branch.remote:
            self.git.push_delete(branch.name)

    def _start_workspace(self, task: ws.Task, base: str | None) -> ws.Workspace:
        if task.state != "open":
            raise WorkError(ErrorCode.TASK_CLOSED, f"Issue #{task.number} は閉じています。",
                            hint="作業を再開するには、GitHubでIssueを開き直してください。")
        if not self.git.working_tree().clean:
            raise WorkError(
                ErrorCode.DIRTY_WORKING_TREE,
                "未コミットの変更があるため、作業空間を作れません（別のIssueの作業に混ざるのを防ぐため）。",
                hint=f"変更をコミットするか、{self._op('stash')} で退避してから実行してください。",
            )
        branch = ws.workspace_branch(task.number)
        if self.git.has_local_branch(branch):
            # 既にある作業空間へ戻る
            self.git.switch(branch)
        else:
            start = self._base_start_point(base)
            if self.git.has_remote_branch(branch):
                start = f"{_git.REMOTE}/{branch}"
            self.git.create_branch(branch, start, switch=True)
            self.git.set_config(ws.base_key(branch), (base or self.default_base))
            if self.git.has_remote_branch(branch):
                self.git.set_upstream(branch)
        workspace = self.current_workspace()
        assert workspace is not None
        return workspace

    def __repr__(self) -> str:
        return f"Repository({str(self.root)!r})"
