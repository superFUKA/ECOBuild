"""Repository の一部：最新化・退避・取り消し。

Repository（repository.py）がこのクラスを継承する。self は Repository。
"""

from __future__ import annotations

from collections.abc import Callable

from . import git as _git
from . import workspace as ws
from .errors import ErrorCode, WorkError
from ._shared import _stash_branch, _markers_in


class Syncing:
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
                hint=f"{self._op('task prune')} {workspace.number} で片付けて {workspace.base} へ移ってください。"
                     "続きの作業は新しいIssueで行います。",
            )
        self.git.fetch()
        self.check_repository()
        self._tidy_finished()
        merged = []
        refs = [f"{_git.REMOTE}/{branch}"]
        if workspace is not None:
            refs.append(f"{_git.REMOTE}/{workspace.base}")
        for ref in refs:
            if self.git.rev_parse(ref) is None:
                continue
            # 作業空間でないブランチは早送りだけ（コミットはPRのマージでだけ入る）。
            try:
                outcome = self.git.merge(ref, ff_only=workspace is None,
                                         message=None if workspace is None else f"{ref} を取り込み")
            except WorkError as error:
                if error.code == ErrorCode.NOT_FAST_FORWARD:
                    # ECOBuildの操作では起きない（作業空間でないブランチにはコミットしない）。
                    error.hint = ("ECOBuildでは作業空間でないブランチにコミットしないため、gitを直接使った結果と"
                                  "考えられます。gitで直してください（手元にだけあるコミットは details）。")
                    error.details = self.git.output("log", "--format=%h %s", f"{ref}..{branch}").splitlines()
                raise
            if not outcome.merged:
                raise WorkError(
                    ErrorCode.MERGE_CONFLICT,
                    f"{ref} の取り込みで衝突しました。",
                    hint=f"衝突したファイルを直して {self._op('sync continue')} で完了してください"
                         f"（直したファイルは自動で登録します）。やめる場合は {self._op('sync abort')}。",
                    details=list(outcome.conflicted),
                )
            if not outcome.already_up_to_date:
                merged.append(ref)
        return ws.SyncResult(branch, tuple(merged), self.hooks.after_sync(self))

    def resolve_conflicts(self, *, skip: Callable[[str], bool] | None = None) -> tuple[str, ...]:
        """衝突したファイルのうち、衝突の印がなくなったものを解決済みとして登録する（消したものは削除として）。

        印が残っていれば何も登録せずに止める。skip に当たるもの（利用側が作り直す生成ファイル等）は触らない。
        登録したものを返す。
        """
        conflicted = [p for p in self.git.working_tree().conflicted if skip is None or not skip(p)]
        markers = [m for p in conflicted for m in _markers_in(self.root / p, p)]
        if markers:
            raise WorkError(ErrorCode.CONFLICT_MARKERS,
                            f"衝突の印（<<<<<<< 等）が残っています（{len(markers)} か所）。",
                            hint=f"印の場所を直して、もう一度 {self._op('sync continue')} を実行してください"
                                 f"（やめる場合は {self._op('sync abort')}）。", details=markers)
        removed = [p for p in conflicted if not (self.root / p).exists()]
        kept = [p for p in conflicted if p not in removed]
        if kept:
            self.git.run("add", "--", *kept)
        if removed:
            self.git.run("rm", "--quiet", "--cached", "--", *removed)
        return tuple(conflicted)

    def continue_sync(self) -> ws.SyncResult:
        """衝突を解決した後、止まっている取り込み（または作業空間の作り直し）を完了する。

        衝突したファイルは、印がなくなっていれば登録してから続ける（resolve_conflicts）。
        """
        branch = self.git.current_branch() or ""
        if self.git.is_rebasing() or self.git.is_merging():
            self.resolve_conflicts()
            self._refuse_conflict_markers(self.git.conflict_markers(cached=True))
        if self.git.is_rebasing():
            outcome = self.git.rebase_continue()
            if not outcome.merged:
                raise WorkError(ErrorCode.MERGE_CONFLICT, "続きの載せ替えで衝突しました。",
                                hint=f"ファイルを直して、もう一度 {self._op('sync continue')}。",
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
        """最後に退避した変更を戻す。

        別の作業空間で退避したものは戻さない（変更が別のIssueの作業に混ざるのを防ぐ。task start と同じ考え方）。
        作業空間でないブランチ（main等）で退避したものは、作業空間へ戻してよい（誤って始めた変更の持ち込み）。
        """
        entries = self.git.stash_list()
        if not entries:
            raise WorkError(ErrorCode.NO_STASH, "退避した変更はありません。")
        source = _stash_branch(entries[0].message)
        current = self.git.current_branch()
        if source is not None and ws.is_workspace_branch(source) and source != current:
            raise WorkError(
                ErrorCode.UNFINISHED_WORK,
                f"最後に退避した変更は作業空間 {source} のものです（今は {current or '切り離された状態'}）。",
                hint=f"{self._op('task start')} {ws.workspace_number(source)} で戻ってから {self._op('stash pop')} "
                     "してください。",
            )
        outcome = self.git.stash_pop()
        if not outcome.merged:
            # 作業空間でないブランチでは add できない。登録を外せば（restore --staged）解決済みになる。
            mark = (f"{self._op('task add')} で登録" if self.current_workspace() is not None
                    else f"{self._op('restore')} --staged <パス> で解決済みに")
            raise WorkError(ErrorCode.MERGE_CONFLICT, "退避した変更を戻すときに衝突しました。",
                            hint=f"衝突したファイルを直して {mark}してください。退避した変更は残っているので、"
                                 f"解決したら {self._op('stash drop')} で捨ててください。",
                            details=list(outcome.conflicted))
        return ws.StashResult(True, self._stash_messages())

    def stash_drop(self) -> ws.StashResult:
        if not self.git.stash_list():
            raise WorkError(ErrorCode.NO_STASH, "退避した変更はありません。")
        self.git.run("stash", "drop", "--quiet")
        return ws.StashResult(False, self._stash_messages())

    def stashes(self) -> tuple[str, ...]:
        return self._stash_messages()

    def restore(self, *paths: str, staged: bool = False) -> ws.RestoreResult:
        self.git.restore(paths, staged=staged)
        return ws.RestoreResult(paths, staged)
