"""Repository の一部：最新化・退避・取り消し。

Repository（repository.py）がこのクラスを継承する。self は Repository。
"""

from __future__ import annotations

from collections.abc import Callable

from . import git as _git
from . import model as wm
from .errors import ErrorCode, WorkError
from ._shared import _stash_branch, _markers_in


class Syncing:
    # 最新化・退避・取り消し ------------------------------------------------------

    def sync(self) -> wm.SyncResult:
        """GitHubの最新を取り込む。タスクブランチでないブランチは早送り、タスクブランチは作成元の最新も取り込む。"""
        if self.git.is_merging() or self.git.is_rebasing():
            raise self._in_progress_error()
        branch = self.git.current_branch()
        if branch is None:
            raise WorkError(ErrorCode.GIT_ERROR, "ブランチにいません（切り離された状態です）。")
        task_branch = self.current_task_branch()
        issue = self.github.get_issue(self.root, task_branch.number) if task_branch is not None else None
        if issue is not None and issue.state != "open":
            # 反映済みのタスクブランチへ作成元を取り込むと、squashマージのため衝突や余分なコミットになる。
            raise WorkError(
                ErrorCode.TASK_CLOSED,
                f"Issue #{task_branch.number} は閉じているため、タスクブランチ {task_branch.branch} は取り込みの対象外です。",
                hint=f"{self._op('task prune')} {task_branch.number} で片付けて {task_branch.base} へ移ってください。"
                     "続きの作業は新しいIssueで行います。",
            )
        self.git.fetch()
        self.check_repository()
        self._tidy_finished()
        merged = []
        refs = [f"{_git.REMOTE}/{branch}"]
        if task_branch is not None:
            refs.append(f"{_git.REMOTE}/{task_branch.base}")
            merge_from = wm.issue_merge_from(issue.body)
            if merge_from:   # 衝突を直すタスク：取り込むブランチも（衝突はここで直す）
                refs.append(f"{_git.REMOTE}/{merge_from}")
        for ref in refs:
            if self.git.rev_parse(ref) is None:
                continue
            # タスクブランチでないブランチは早送りだけ（コミットはPRのマージでだけ入る）。
            try:
                outcome = self.git.merge(ref, ff_only=task_branch is None,
                                         message=None if task_branch is None else f"{ref} を取り込み")
            except WorkError as error:
                if error.code == ErrorCode.NOT_FAST_FORWARD:
                    # ECOBuildの操作では起きない（タスクブランチでないブランチにはコミットしない）。
                    error.hint = ("ECOBuildではタスクブランチでないブランチにコミットしないため、gitを直接使った結果と"
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
        return wm.SyncResult(branch, tuple(merged), self.hooks.after_sync(self))

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

    def continue_sync(self) -> wm.SyncResult:
        """衝突を解決した後、止まっている取り込み（またはタスクブランチの作り直し）を完了する。

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
            return wm.SyncResult(branch, ("rebase",), self.hooks.after_sync(self))
        if self.git.is_merging():
            self.git.merge_continue()
            return wm.SyncResult(branch, ("merge",), self.hooks.after_sync(self))
        raise WorkError(ErrorCode.NO_SYNC_IN_PROGRESS, "止まっている取り込みはありません。")

    def abort_sync(self) -> None:
        if self.git.is_rebasing():
            self.git.rebase_abort()
        elif self.git.is_merging():
            self.git.merge_abort()
        else:
            raise WorkError(ErrorCode.NO_SYNC_IN_PROGRESS, "止まっている取り込みはありません。")

    def stash(self) -> wm.StashResult:
        stashed = self.git.stash_push()
        return wm.StashResult(stashed, self._stash_messages())

    def _own_stash(self) -> int:
        """このブランチで退避した、いちばん新しい変更の番号（stash@{n}）。

        退避（refs/stash）は作業空間どうしで共有なので、別のタスクブランチ（ほかの作業空間）で退避したものは選ばない
        （変更が別のIssueの作業に混ざるのを防ぐ。task start と同じ考え方）。元の clone 等（その場で切り替える所）では、
        タスクブランチでないブランチ（main等）で退避したものもタスクブランチへ戻してよい（誤って始めた変更の持ち込み）。
        """
        entries = self.git.stash_list()
        if not entries:
            raise WorkError(ErrorCode.NO_STASH, "退避した変更はありません。")
        current = self.git.current_branch()
        carry = not self.git.is_linked_worktree()
        if carry:
            # 退避のメッセージにはブランチ名しかないので、ほかの作業ツリー（確認用の作業空間＝切り離された状態・人が作った
            # 作業ツリー）で退避したかもしれないものは持ち込まない：切り離された状態のもの（ほかに作業ツリーがあるとき）と、
            # 今ほかの作業ツリーが取り出しているブランチのもの
            others = {branch for branch, path in self.git.checked_out_branches().items()
                      if not _git.same_path(path, self.root)}
            detached_elsewhere = len(self.git.worktrees()) > 1
        for entry in entries:
            source = _stash_branch(entry.message)
            if source == current or (carry and (
                    not detached_elsewhere if source is None
                    else not wm.is_task_branch(source) and source not in others)):
                return entry.index
        source = _stash_branch(entries[0].message)
        if source is not None and wm.is_task_branch(source):
            raise WorkError(
                ErrorCode.UNFINISHED_WORK,
                f"最後に退避した変更はタスクブランチ {source} のものです（今は {current or '切り離された状態'}）。",
                hint=f"{self._op('task start')} {wm.task_number(source)} で戻ってから {self._op('stash pop')} "
                     "してください。",
            )
        raise WorkError(ErrorCode.NO_STASH, f"{current or 'ここ'} で退避した変更はありません（ほかのブランチのものだけです）。")

    def stash_pop(self) -> wm.StashResult:
        """このブランチで最後に退避した変更を戻す（ほかのタスクブランチのものは戻さない：_own_stash）。"""
        index = self._own_stash()
        outcome = self.git.stash_pop(index)
        if not outcome.merged:
            # タスクブランチでないブランチでは add できない。登録を外せば（restore --staged）解決済みになる。
            mark = (f"{self._op('task add')} で登録" if self.current_task_branch() is not None
                    else f"{self._op('restore')} --staged <パス> で解決済みに")
            raise WorkError(ErrorCode.MERGE_CONFLICT, "退避した変更を戻すときに衝突しました。",
                            hint=f"衝突したファイルを直して {mark}してください。退避した変更は残っているので、"
                                 f"解決したら {self._op('stash drop')} で捨ててください。",
                            details=list(outcome.conflicted))
        return wm.StashResult(True, self._stash_messages())

    def stash_drop(self) -> wm.StashResult:
        """このブランチで最後に退避した変更を捨てる（ほかのタスクブランチのものは捨てない：_own_stash）。"""
        index = self._own_stash()
        self.git.run("stash", "drop", "--quiet", f"stash@{{{index}}}")
        return wm.StashResult(False, self._stash_messages())

    def stashes(self) -> tuple[str, ...]:
        return self._stash_messages()

    def restore(self, *paths: str, staged: bool = False, source: str | None = None) -> wm.RestoreResult:
        """変更を取り消す。source：ファイルを以前の版（コミット）の状態に戻す（タスクブランチで。結果は未コミットの変更になり、
        いつものようにコミットする。履歴は消さない）。paths を省くと全体。
        staged も source もなければ、ファイルを最後のコミットの状態にする（ステージした変更も取り消す。コミットに
        なかったファイル＝追加したファイルは消える。未追跡のファイルも、名前を挙げたものは消す）。"""
        if source is None and staged:
            self.git.restore(paths, staged=True)
            return wm.RestoreResult(paths, True)
        if source is None:
            untracked = set(self.git.working_tree().untracked)
            tracked = tuple(p for p in paths if p.replace("\\", "/") not in untracked)
            if not paths:
                self.git.restore(paths)          # 全体は消さない（git がファイルを求めるエラーになる、以前のとおり）
            elif tracked:
                self.git.restore(tracked, source="HEAD")
            for path in paths:
                if path.replace("\\", "/") in untracked:
                    (self.root / path).unlink(missing_ok=True)
            return wm.RestoreResult(paths, False)
        self.require_task_branch("以前の版の状態に戻すこと")
        commit = self._commit(source)
        tree = self.git.working_tree()
        if tree.staged or tree.unstaged or tree.conflicted:
            raise WorkError(ErrorCode.DIRTY_WORKING_TREE, "未コミットの変更があります（戻すと失われます）。",
                            hint=f"先に {self._op('task commit')} でコミットするか、{self._op('stash')} で退避してください。")
        self.git.restore(paths, source=commit)
        return wm.RestoreResult(paths or (".",), False, commit)

    def reset_task(self, revision: str, *, keep: bool = False, dry_run: bool = False) -> wm.ResetResult:
        """タスクブランチを以前の版まで戻す（その後のコミットを捨てる）。まだ GitHub に push していないコミットだけ
        捨てられる（push 済みを消すと、GitHub やほかの人とずれる：その時は restore --source で戻してコミットする）。
        keep：ファイルはそのままにして、捨てたコミットの変更をコミットしていない変更として残す（コミットの取り消し）。"""
        task_branch = self.require_task_branch("タスクブランチを以前の版まで戻すこと")
        commit = self._commit(revision)
        if not self.git.is_ancestor(commit, "HEAD"):
            raise WorkError(ErrorCode.REVISION_NOT_FOUND, f"{revision} は {task_branch.branch} のコミットにありません。",
                            hint=f"{self._op('log')} で、戻す先のコミットを確かめてください。")
        base = f"{_git.REMOTE}/{task_branch.base}" if self.git.rev_parse(f"{_git.REMOTE}/{task_branch.base}") else task_branch.base
        fork = self.git.output("merge-base", "HEAD", base)
        if not self.git.is_ancestor(fork, commit):
            raise WorkError(ErrorCode.REVISION_NOT_FOUND, f"{revision} は、このタスクブランチを作る前（作成元 {task_branch.base}）のコミットです。",
                            hint=f"その版のファイルに戻すには {self._op('restore')} --source {revision}（変更としてコミットします）。")
        lines = self.git.output("log", "--format=%H%x1f%s", f"{commit}..HEAD").splitlines()
        dropped = tuple(tuple(line.split("\x1f", 1)) for line in lines if line)
        upstream = f"{_git.REMOTE}/{task_branch.branch}"
        if dropped and self.git.rev_parse(upstream) and self.git.count(f"{commit}..{upstream}"):
            raise WorkError(ErrorCode.COMMITS_WOULD_BE_LOST, "捨てるコミットの中に、GitHub に push 済みのものがあります。",
                            hint=f"push 済みのコミットは消さずに、{self._op('restore')} --source {revision} でその版のファイルに戻し、"
                                 "変更としてコミットしてください。")
        tree = self.git.working_tree()
        if dropped and keep and (tree.conflicted or self.git.is_merging()):
            raise WorkError(ErrorCode.DIRTY_WORKING_TREE, "取り込みの途中です（衝突を解決するか、取り込みを中止してから戻します）。")
        if dropped and not keep and (tree.staged or tree.unstaged or tree.conflicted):
            raise WorkError(ErrorCode.DIRTY_WORKING_TREE, "未コミットの変更があります（戻すと失われます）。",
                            hint=f"先に {self._op('task commit')} でコミットするか、{self._op('stash')} で退避してください。"
                                 "コミットの変更を手元に残すなら --keep。")
        if dropped and not dry_run:
            if keep:
                self.git.reset_mixed(commit)   # 今の変更（ステージしたものも）は、変更のまま残る
            else:
                self.git.reset_hard(commit)
        return wm.ResetResult(task_branch.branch, commit, dropped, dry_run, keep)

    def _commit(self, revision: str) -> str:
        found = self.git.rev_parse(revision)
        if found is None:
            raise WorkError(ErrorCode.REVISION_NOT_FOUND, f"コミット {revision} が見つかりません。",
                            hint=f"{self._op('log')} で、コミット（の先頭の数文字）を確かめてください。")
        return found
