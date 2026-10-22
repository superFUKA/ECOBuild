"""Repository の一部：提出と完了（番号はタスクの番号。PRはその実現の方法）。

Repository（repository.py）がこのクラスを継承する。self は Repository。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from ecotask import board as _board
from . import git as _git
from . import model as wm
from .errors import ErrorCode, WorkError
from ._shared import _PR_IN_SUBJECT


class Completion:
    # 提出と完了（番号はタスクの番号。PRはその実現の方法） ------------------------------------

    def submission(self, number: int) -> wm.PullRequest | None:
        """タスクの開いている提出（タスクブランチのPR）。なければNone。開いているものは1つ（あれば最新のもの）。"""
        opened = [p for p in self.github.pull_requests_for_branch(self.root, self._task_branch_of(number))
                  if p.state == "open"]
        return wm.PullRequest._from(self, max(opened, key=lambda p: p.number)) if opened else None

    def require_submission(self, number: int) -> wm.PullRequest:
        pr = self.submission(number)
        if pr is None:
            raise WorkError(ErrorCode.NO_PULL_REQUEST, f"タスク #{number} の提出はありません。",
                            hint=f"タスク #{number} のタスクブランチで {self._op('task submit')} を実行して提出します。")
        return pr

    def review_task(self, number: int, place: Path | str, *,
                    open: Callable[[Path], "Repository"] | None = None) -> wm.ReviewResult:
        """タスクの提出を、確認用の作業空間 place に取り出す（review_in と同じ。番号はタスクの番号）。"""
        return self.review_in(self.require_submission(number).number, place, open=open)

    def withdraw(self, number: int | None = None) -> wm.PullRequest:
        """提出を取り下げて作業中に戻す（PRを閉じる。タスクブランチは残る。もう一度 task submit で出し直せる）。"""
        if number is None:
            number = self.require_task_branch("番号を省略した提出の取り下げ").number
        pr = self.require_submission(number)
        self.github.close_pull_request(self.root, pr.number)
        self.tracker.set_stage(number, _board.IN_PROGRESS)
        return self.pull_request(pr.number)

    def reject(self, number: int, message: str) -> wm.JudgeResult:
        """差し戻す（修正を依頼する）。確認用の作業空間（task review）があれば消す。"""
        if not message.strip():
            raise WorkError(ErrorCode.INVALID_ARGUMENT, "差し戻す理由が必要です。",
                            hint="--message で、直してほしいことを書いてください。")
        pr = self.require_submission(number)
        self.require_take_in(pr.base, "差し戻し")
        self._judge(pr, "request_changes", message)
        self.tracker.set_stage(number, _board.IN_PROGRESS)  # 直すのは作業者。出し直し（task submit）でレビュー待ちに戻る
        return wm.JudgeResult(number, pr.number, pr.url, self._leave_review(pr.number))

    def approve(self, number: int, message: str = "", **finish_options) -> wm.FinishResult:
        """承認し、そのまま完了する（finish と同じ手順）。確認用の作業空間（task review）があれば、先に消す。"""
        pr = self.require_submission(number)
        if pr.draft:
            raise WorkError(ErrorCode.PULL_REQUEST_DRAFT, f"タスク #{number} の提出は下書きです。",
                            hint="作業者が準備できたら task submit で下書きを解除します。")
        self.require_take_in(pr.base, "承認")
        self._judge(pr, "approve", message)
        removed = self._leave_review(pr.number)
        result = self.finish(number, **finish_options)
        return replace(result, approved=True, review_removed=removed or result.review_removed)

    def finish(self, number: int | None = None, *, wait: bool = True, ignore_checks: bool = False,
               subject: str | None = None, partial: bool | None = None, timeout: float = 1800,
               sleep: Callable[[float], None] = time.sleep,
               clock: Callable[[], float] = time.monotonic) -> wm.FinishResult:
        """タスクを完了する：未pushのコミットを送る → 提出がなければ作る → CIを待つ → （承認が必須なら確かめる）→
        squashで取り込み、Issueを閉じ、GitHubのブランチを消す → 手元のタスクブランチを片付ける。

        partial：True なら取り込んだ後もタスクを閉じず、タスクブランチを作成元の最新から作り直して続ける（中間の取り込み）。
        False なら閉じる。開いている提出の中間提出か（本文の Refs／Closes）は、これに合わせて書き換える。None なら提出のまま
        （task approve。提出がなければ閉じる）。中間提出を取り込んだ後、新しい変更がなければ、取り込むものなしで閉じる。
        どこで止まっても、もう一度実行すれば続きから行う。wait：CIを待つ（False なら、実行中なら止める）。
        ignore_checks：CIの失敗を承知で取り込む（待たない）。subject：取り込むコミットの件名（既定は題名）。
        """
        if number is None:
            number = self.require_task_branch("番号を省略したタスクの完了").number
        review_removed = None
        reviewing = self._reviewing()
        if reviewing is not None and self._task_of_pull_request(reviewing) == number:
            # その提出の確認用の作業空間（task review）の中なら、先に消す（元の clone へ移る）。消せなくても完了は進める
            review_removed = self._leave_review(reviewing)
        result = self._finish(number, wait=wait, ignore_checks=ignore_checks, subject=subject, partial=partial,
                              timeout=timeout, sleep=sleep, clock=clock)
        return replace(result, review_removed=review_removed) if review_removed else result

    def _finish(self, number: int, *, wait: bool, ignore_checks: bool, subject: str | None, partial: bool | None,
                timeout: float, sleep: Callable[[float], None], clock: Callable[[], float]) -> wm.FinishResult:
        branch = self._task_branch_of(number)
        here = self.git.current_branch() == branch
        self._guard_removal(branch, "完了（GitHubのタスクブランチを消す）", switching=False)   # ここで切り替えられないときは、取り込みの後に残す
        if here:
            tree = self.git.working_tree()
            if tree.staged or tree.unstaged or tree.conflicted or self.git.is_merging():
                raise WorkError(ErrorCode.DIRTY_WORKING_TREE, "未コミットの変更があるため、完了できません。",
                                hint=f"{self._op('task commit')} --message \"…\" で記録してから、もう一度実行してください。",
                                details=list(dict.fromkeys(tree.staged + tree.unstaged + tree.conflicted)))
        self.git.fetch()
        issue = self.github.get_issue(self.root, number)
        pr = self.submission(number)
        if issue.state == "open" and self.git.has_local_branch(branch):
            self._push_if_ahead(branch)
            if pr is not None:
                pr = self.submission(number)
        if pr is None and issue.state == "open":
            last = self._merged_and_unchanged(number, branch)
            if last is not None and last.partial and not partial:
                return self._close_after_partial(number, branch, last)
            if last is None or last.partial:
                pr = self._submit_for_finish(number, branch, here, partial=bool(partial))
        if pr is None:
            return self._resume_finish(number, branch)
        if partial is not None and pr.partial != partial:
            body = self.github.get_pull_request(self.root, pr.number).body
            self.github.edit_pull_request(self.root, pr.number, body=wm.with_link_kind(body, number, partial=partial))
            pr = self.submission(number)
        if pr.draft:
            raise WorkError(ErrorCode.PULL_REQUEST_DRAFT, f"タスク #{number} の提出は下書きです。",
                            hint=f"準備ができたら、タスクブランチで {self._op('task submit')} を実行して下書きを解除してください。")
        self.require_take_in(pr.base, "取り込み")
        checks: tuple = ()
        if wait and not ignore_checks and self._has_workflows():
            try:
                checks = tuple(self.ci_wait(pr.number, timeout=timeout, sleep=sleep, clock=clock))
            except WorkError as error:
                if error.code in (ErrorCode.NO_CI_RUN, ErrorCode.CHECKS_PENDING):
                    error.hint = f"{error.hint} 待たずに完了するなら --no-wait（実行中なら止まります）。"
                elif error.code == ErrorCode.CHECKS_FAILED:
                    error.hint = (f"{self._op('ci logs')} で失敗した手順のログを確認し、直して {self._op('task commit')} の後、"
                                  f"もう一度 {self._op('task finish')} {number}。失敗を承知で完了するなら --ignore-checks。")
                raise
        if self.require_approval and not self._approved(pr.number):
            raise WorkError(ErrorCode.APPROVAL_REQUIRED, f"タスク #{number} の提出はまだ承認されていません"
                                                         "（このモジュールは承認が必須です）。",
                            hint=f"見る人が {self._op('task review')} {number} で確かめ、{self._op('task approve')} "
                                 f"{number} で承認・完了します。")
        try:
            merged = self._merge_pull_request(pr.number, ignore_checks=ignore_checks, subject=subject)
        except WorkError as error:
            if error.code == ErrorCode.APPROVAL_REQUIRED:
                error.message = f"タスク #{number} は、ブランチの保護の条件（承認・CI）を満たしていないため、取り込めません。"
                error.hint = (f"見る人が {self._op('task review')} {number} で確かめ、{self._op('task approve')} {number} "
                              f"で承認・完了します（設定は {self._op('module protect')} --show）。")
            raise
        return self._after_finish(number, branch, pr, merged, checks, subject or pr.title)

    def _merged_and_unchanged(self, number: int, branch: str) -> wm.PullRequest | None:
        """取り込んだ最後の提出。その後タスクブランチに新しいコミットがなければ返す（あれば None）。

        最後の提出（中間提出でないもの）なら、取り込みの後処理の途中で止まった状態（もう一度 finish すれば、新しい提出を
        作らずに後処理の続きを行う）。中間提出なら、続きの作業がまだない状態（finish すれば、そのまま閉じる）。"""
        merged = [p for p in self.github.pull_requests_for_branch(self.root, branch) if p.state == "merged"]
        if not merged:
            return None
        local, remote = self.git.has_local_branch(branch), self.git.has_remote_branch(branch)
        base = (self.git.get_config(wm.base_key(branch)) if local else None) or self._recorded_base(number, branch) \
            or self.default_base
        if self._lost_commits(branch, base, local=local, remote=remote):
            return None
        return wm.PullRequest._from(self, max(merged, key=lambda p: p.number))

    def _close_after_partial(self, number: int, branch: str, last: wm.PullRequest) -> wm.FinishResult:
        """中間提出を取り込んだ後、新しい変更がないまま完了する：取り込むものはないので、タスクを閉じて片付けるだけ。"""
        self.tracker.check_finishable(number, action="完了")
        title = self.github.get_issue(self.root, number).title
        self.github.close_issue(self.root, number)
        if self.git.has_remote_branch(branch):
            self.git.push_delete(branch)
        self.tracker.closed(number)
        removed, released = self._clean_finished(branch)
        return wm.FinishResult(number, last.number, last.url, title, False, False, number, False, removed,
                               released.switched_to, (), self._upcoming(), workspace_removed=released.workspace_removed,
                               workspace_kept=released.kept)

    def _resume_finish(self, number: int, branch: str) -> wm.FinishResult:
        """Issueが閉じ、開いている提出がないタスク：取り込みの後処理と手元の片付けの残りだけを行う。
        残りがなければ（完了済み）、何もせずに already_done の結果を返す。"""
        merged = [p for p in self.github.pull_requests_for_branch(self.root, branch) if p.state == "merged"]
        if not merged:
            raise WorkError(ErrorCode.TASK_CLOSED, f"タスク #{number} は閉じています（取り込んだ提出はありません）。",
                            hint=f"タスクブランチが残っていれば {self._op('task prune')} {number} で片付けられます。")
        info = max(merged, key=lambda p: p.number)
        pr = wm.PullRequest._from(self, info)
        try:
            result = self._finish_merge(pr, info, resumed=True)
        except WorkError as error:
            if error.code != ErrorCode.PULL_REQUEST_NOT_OPEN:
                raise
            result = wm.MergeResult(pr.number, "squash", None, False, True)
        finished = self._after_finish(number, branch, pr, result, (), pr.title)
        if not (result.closed_issue or finished.removed):
            # 前の完了で済んでいる：もう一度打っても誤りにしない（何もしなかったことを already_done で返す）
            return replace(finished, resumed=False, already_done=True)
        return finished

    def _after_finish(self, number: int, branch: str, pr: wm.PullRequest, merged: wm.MergeResult,
                      checks: tuple, subject: str) -> wm.FinishResult:
        removed, released, upcoming = False, wm.Released(False), None
        if not pr.partial:
            removed, released = self._clean_finished(branch)
            upcoming = self._upcoming()
        return wm.FinishResult(number, pr.number, pr.url, subject, pr.partial, merged.resumed, merged.closed_issue,
                               merged.branch_rebuilt, removed, released.switched_to, checks, upcoming,
                               workspace_removed=released.workspace_removed, workspace_kept=released.kept)

    def _push_if_ahead(self, branch: str) -> None:
        """手元のブランチに、GitHubにないコミットがあれば送る。"""
        remote = self.git.has_remote_branch(branch)
        if remote and self.git.count(f"{_git.REMOTE}/{branch}..{branch}") == 0:
            return
        self.git.push(branch, set_upstream=not remote)

    def _submit_for_finish(self, number: int, branch: str, here: bool, *, partial: bool) -> wm.PullRequest:
        """完了の前に、提出がなければ作る（レビューなしで完了するとき。PRは履歴として残る）。"""
        local, remote = self.git.has_local_branch(branch), self.git.has_remote_branch(branch)
        if not (local or remote):
            raise WorkError(ErrorCode.BRANCH_NOT_FOUND, f"タスク #{number} のタスクブランチがありません。",
                            hint=f"{self._op('task start')} {number} でタスクブランチを作り、変更を記録してから完了します"
                                 f"（コードを変えないタスクなら {self._op('task close')} {number}）。")
        if here:
            self.hooks.before_submit(self)
        base = (self.git.get_config(wm.base_key(branch)) if local else None) or self._recorded_base(number, branch) \
            or self.default_base
        head, base_ref = f"{_git.REMOTE}/{branch}", f"{_git.REMOTE}/{base}"
        if self.git.count(f"{base_ref}..{head}") == 0 or not self.git.has_changes(base_ref, head):
            raise WorkError(ErrorCode.NOTHING_TO_SUBMIT, f"タスク #{number} には、{base} へ取り込む変更がありません。",
                            hint=f"変更を {self._op('task commit')} で記録してから実行してください（変更が要らないなら "
                                 f"{self._op('task close')} {number}）。")
        self._refuse_conflict_markers(self.git.conflict_markers(f"{base_ref}...{head}"), committed=True)
        return self._create_submission(number, branch, base, title=None, partial=partial, draft=False)

    def _create_submission(self, number: int, branch: str, base: str, *, title: str | None, partial: bool,
                           draft: bool, reviewers: tuple[str, ...] = (),
                           sections: dict[str, str] | None = None) -> wm.PullRequest:
        issue = self.github.get_issue(self.root, number)
        info = self.github.create_pull_request(
            self.root, head=branch, base=base, title=title or issue.title,
            body=wm.with_sections(wm.with_task_link("", number, partial=partial), sections or {}), draft=draft,
        )
        if reviewers:
            self.github.edit_pull_request(self.root, info.number, add_reviewers=reviewers)
        self.tracker.set_stage(number, _board.IN_PROGRESS if draft else _board.IN_REVIEW)
        pr = wm.PullRequest._from(self, info)
        if not pr.partial:
            try:
                self.tracker.check_finishable(number)
            except WorkError as error:
                self.notices.append(f"タスク #{number} は、子タスクが終わるまで完了できません"
                                    f"（{', '.join(error.details)}）。")
        return pr

    def _clean_finished(self, branch: str) -> tuple[bool, wm.Released]:
        """完了したタスクの手元のタスクブランチを片付ける：取り出している作業空間を消してから、ブランチを消す
        （元の clone 等がその場で取り出していれば、作成元へ移って最新にする）。失われるコミットがある・作業空間が
        使用中（ロック中）・未コミットの変更があるなら残して知らせる。(消したか, 作業空間の扱い) を返す。"""
        if not self.git.has_local_branch(branch):
            return False, wm.Released(False)
        reason = self._unsafe_to_remove(branch)
        if reason is not None:
            self.notices.append(f"手元のタスクブランチ {branch} は残しました（{reason}）。")
            return False, wm.Released(False, kept=reason)
        released = self._release_branch(branch, action="完了したタスクブランチの片付け")
        if not released.released:
            self.notices.append(f"手元のタスクブランチ {branch} は残しました（{released.kept}）。")
            return False, released
        self.git.delete_branch(branch, force=True)
        self.git.unset_config(wm.base_key(branch))
        return True, released

    def _upcoming(self) -> wm.TaskRef | None:
        """次のタスクの候補（task next の1番目）。調べられなければNone（知らせるだけなので）。"""
        try:
            ranked = self.next_tasks(assignee="@me", count=1)
        except WorkError:
            return None
        return wm.TaskRef(ranked[0].task.number, ranked[0].task.title, ranked[0].task.state) if ranked else None

    def _approved(self, pull_request: int) -> bool:
        """承認されているか（人ごとの最後の判定に、承認があり、修正依頼がない）。"""
        latest = {}
        for review in self.github.pull_request_activity(self.root, pull_request).reviews:
            if review.state in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
                latest[review.author] = review.state
        return "APPROVED" in latest.values() and "CHANGES_REQUESTED" not in latest.values()

    def _judge(self, pr: wm.PullRequest, event: str, message: str) -> None:
        try:
            self.github.review_pull_request(self.root, pr.number, event=event, body=message)
        except WorkError as error:
            if error.code == ErrorCode.OWN_PULL_REQUEST:
                task = wm.task_number(pr.head)
                error.message = "自分の提出は承認・差し戻しできません（GitHubの制限）。"
                error.hint = (f"自分で完了するなら {self._op('task finish')} {task}、やめるなら "
                              f"{self._op('task withdraw')} {task}。")
            if self._review_workspaces().get(pr.number) is not None:   # 確認用の作業空間を残さない
                removed = self._leave_review(pr.number)
                error.hint += (f"確認用の作業空間 {removed} を消しました。" if removed else
                               f"確認用の作業空間が残っています。{self._op('task review')} --done で消せます。")
            raise

    def _leave_review(self, pull_request: int) -> Path | None:
        """その提出の確認用の作業空間（task review）があれば消す。消した場所（なければ・消せなければNone。消せない
        わけは notices で知らせる）。"""
        place = self._review_workspaces().get(pull_request)
        if place is None:
            return None
        try:
            return self._end_review_at(pull_request, place).workspace
        except WorkError as error:   # 消せればよいだけ（判定は出した後）：わけ（使用中・変更あり・他のプログラムが使用中等）を知らせて進む
            self.notices.append(f"確認用の作業空間 {place} は残しました（{error.message}）。"
                                f"{self._op('task review')} --done で消せます。")
            return None

    def _tidy_finished(self) -> tuple[str, ...]:
        """完了したタスクの手元のタスクブランチ（GitHubのブランチがなく、Issueが閉じたもの）を片付ける。今いるもの・
        ほかの作業ツリー（元の clone・作業空間）が取り出しているものは除く。

        fetch の後に呼ぶ。失われるコミットがあれば残す（task prune と同じ）。
        """
        try:
            self.git.forget_missing_worktrees()   # 先に、フォルダーがなくなった作業空間の記録を片付ける（ロック中のものも）
        except WorkError:
            pass
        current = self.git.current_branch()
        remote = set(self.git.remote_branches())
        checked_out = self.git.checked_out_branches()   # ほかの git worktree が使っているブランチは git が消させない
        removed, kept = [], []
        for branch in self.git.local_branches():
            number = wm.task_number(branch)
            if number is None or branch == current or branch in remote \
                    or self.git.get_config(f"branch.{branch}.merge") is None:   # GitHubへ送ったことがないもの
                continue
            try:
                if self.github.get_issue(self.root, number).state != "closed" or self._unsafe_to_remove(branch):
                    continue
            except WorkError:
                continue
            if branch in checked_out or self.hooks.branch_locks(self, branch):   # ほかの作業空間が使っている：残す（次の機会に片付く）
                kept.append(branch)
                continue
            self.git.delete_branch(branch, force=True)
            self.git.unset_config(wm.base_key(branch))
            removed.append(branch)
        if removed:
            self.notices.append(f"完了したタスクの手元のタスクブランチを片付けました：{', '.join(removed)}")
        if kept:
            self.notices.append(f"完了したタスクの手元のタスクブランチ {', '.join(kept)} は、ほかの作業空間が使用中"
                                "（取り出し中・ロック中）のため残しました。")
        return tuple(removed)

    def task_diff(self, number: int | None = None) -> str:
        """タスクの提出の差分。提出がなければ、タスクブランチの作成元との差分。"""
        if number is None:
            number = self.require_task_branch("番号を省略した差分").number
        pr = self.submission(number)
        if pr is not None:
            return self.github.pull_request_diff(self.root, pr.number)
        return self.git.output("diff", "...".join(self._task_ends(number)))

    def task_diff_revisions(self, number: int | None = None) -> tuple[str, str]:
        """task_diff の両端のコミット（作成元から分かれたところ, タスクブランチの先）。差分を別の画面で比べるのに使う。"""
        if number is None:
            number = self.require_task_branch("番号を省略した差分").number
        pr = self.submission(number)
        if pr is not None:
            self.git.fetch()
            base, head = f"{_git.REMOTE}/{pr.base}", f"{_git.REMOTE}/{pr.head}"
        else:
            base, head = self._task_ends(number)
        return self.git.output("merge-base", base, head), self.git.output("rev-parse", head)

    def task_diff_files(self, number: int | None = None) -> tuple[wm.DiffFile, ...]:
        """task_diff の変わったファイル（パス・種類・足した行・消した行・改行コードだけの差か。パスの順）。"""
        base, head = self.task_diff_revisions(number)
        return tuple(wm.DiffFile(*row) for row in sorted(self.git.changed_files(base, head)))

    def _task_ends(self, number: int) -> tuple[str, str]:
        """提出のないタスクの差分の両端（作成元, タスクブランチ。手元になければ GitHub のもの）。"""
        branch = self._task_branch_of(number)
        self.git.fetch()
        local, remote = self.git.has_local_branch(branch), self.git.has_remote_branch(branch)
        if not (local or remote):
            raise WorkError(ErrorCode.BRANCH_NOT_FOUND, f"タスク #{number} のタスクブランチがありません。")
        base = (self.git.get_config(wm.base_key(branch)) if local else None) or self._recorded_base(number, branch) \
            or self.default_base
        return f"{_git.REMOTE}/{base}", branch if local else f"{_git.REMOTE}/{branch}"

    def revert_task(self, number: int) -> wm.RevertResult:
        """完了したタスクの取り込み（中間提出も含めてすべて）を取り消すタスクブランチを作る。提出は task submit で出す。"""
        merged = sorted((p for p in self.github.pull_requests_for_branch(self.root, self._task_branch_of(number))
                         if p.state == "merged" and p.merge_commit), key=lambda p: p.number)
        if not merged:
            raise WorkError(ErrorCode.PULL_REQUEST_NOT_OPEN, f"タスク #{number} には、取り込んだ提出がありません。",
                            hint="取り消せるのは、完了（または中間提出を取り込み）したタスクだけです。")
        title = self.github.get_issue(self.root, number).title
        return self._revert(merged, f"「{title}」を取り消す", f"#{number} の取り込みを取り消す。\n", task=number)

    def merge_branch(self, name: str, *, ignore_checks: bool = False) -> wm.MergeResult:
        """ブランチ同士の提出（branch submit で作ったPR。head が name）を、マージコミットで取り込む。"""
        if wm.is_task_branch(name):
            raise WorkError(ErrorCode.PROTECTED_BRANCH, f"{name} はタスクブランチです。",
                            hint=f"タスクブランチの完了は {self._op('task finish')} です。")
        opened = [p for p in self.github.pull_requests_for_branch(self.root, name) if p.state == "open"]
        if not opened:
            raise WorkError(ErrorCode.NO_PULL_REQUEST, f"{name} の開いている提出（ブランチ同士のPR）がありません。",
                            hint=f"{self._op('branch submit')} {name} --into <取り込み先> で作ります。")
        self.require_take_in(max(opened, key=lambda p: p.number).base, "取り込み")
        return self._merge_pull_request(max(opened, key=lambda p: p.number).number, ignore_checks=ignore_checks)

    def merge_branch_into(self, name: str, into: str) -> wm.BranchMerged:
        """管理用のブランチ name を、管理用のブランチ into へ直接取り込む（PR を作らない）。

        作業（コミット）を直接入れられるのはタスクブランチだけで、管理用のブランチ同士のマージは管理用のブランチの操作
        （作業ではない）なので、提出（PR）を通さなくてよい。GitHub の最新どうしを、手元の作業ツリーに触れずに
        （merge-tree）合わせて into へ push する：早送りできれば早送り、できなければマージコミット。衝突したら何も
        変えずに止める。できるのは into への提出を取り込める人だけ。GitHub のブランチの保護が PR を求めれば、push が
        断られる（branch submit で提出する）。前もって確かめるのは plan_branch_merge。"""
        self._check_branch_merge(name, into)
        self.require_take_in(into, "取り込み")
        head, base = self._branch_merge_ends(name, into)
        method, tree, conflicts = self._branch_merge_tree(head, base)
        if method == "up-to-date":
            raise WorkError(ErrorCode.NOTHING_TO_SUBMIT, f"{name} は {into} に取り込み済みです。")
        if method == "conflict":
            raise WorkError(ErrorCode.MERGE_CONFLICT, f"{name} と {into} が衝突するので、取り込みませんでした（何も変えていません）。",
                            hint=f"{self._op('branch submit')} {name} --into {into} で提出し、衝突を直してから "
                                 f"{self._op('branch merge')} {name} で取り込んでください。", details=list(conflicts))
        if method == "fast-forward":
            commit = head
        else:
            commit = self.git.output("commit-tree", tree, "-p", base, "-p", head, "-m", f"{name} を {into} へ取り込む")
        pushed = self.git.run("push", "--quiet", _git.REMOTE, f"{commit}:refs/heads/{into}", check=False)
        if not pushed.ok:
            raise WorkError(ErrorCode.PROTECTED_BRANCH, f"GitHub が {into} への push を断りました（何も変えていません）。",
                            hint=f"{into} のブランチの保護が PR を求めているなら、{self._op('branch submit')} {name} --into {into} "
                                 f"で提出して {self._op('branch merge')} {name} で取り込みます。",
                            details=pushed.output)
        self.git.fetch()
        return wm.BranchMerged(name, into, method, commit)

    def plan_branch_merge(self, name: str, into: str) -> wm.BranchMergePlan:
        """merge_branch_into を前もって確かめる（何も変えない）：入るコミット・変わるファイル・方法（早送り・マージ
        コミット・衝突・取り込み済み）・衝突するファイル・今のアカウントで取り込めるか。取り込めない人も見られる。"""
        self._check_branch_merge(name, into)
        head, base = self._branch_merge_ends(name, into, reuse=True)
        method, _, conflicts = self._branch_merge_tree(head, base)
        rows = [line.split("\x1f") for line in self.git.output(
            "log", f"--max-count={wm.MERGE_PLAN_COMMITS}", "--format=%H%x1f%s%x1f%an%x1f%ad", "--date=iso-strict",
            f"{base}..{head}").splitlines()]
        commits = tuple(wm.LogEntry(sha, subject, author, date, int(m.group(1)) if (m := _PR_IN_SUBJECT.search(subject)) else None, None)
                        for sha, subject, author, date in rows)
        count = int(self.git.output("rev-list", "--count", f"{base}..{head}"))
        files = tuple(f for f in self.git.output("diff", "--name-only", f"{base}...{head}").splitlines() if f)
        return wm.BranchMergePlan(name, into, method, commits, count, files[:wm.MERGE_PLAN_FILES], len(files), conflicts,
                                  self.can_take_in(into), self.take_in_owners(into))

    def _check_branch_merge(self, name: str, into: str) -> None:
        for branch in (name, into):
            if wm.is_task_branch(branch):
                raise WorkError(ErrorCode.PROTECTED_BRANCH, f"{branch} はタスクブランチです。",
                                hint=f"ブランチ同士のマージは、タスクブランチでないブランチ（main・develop 等）どうしです。"
                                     f"タスクブランチの完了は {self._op('task finish')} です。")
        if name == into:
            raise WorkError(ErrorCode.INVALID_BASE, f"{name} を {name} 自身へは取り込めません。")

    def _branch_merge_ends(self, name: str, into: str, *, reuse: bool = False) -> tuple[str, str]:
        """GitHub の最新の name と into の先頭（取り込むもの, 取り込み先）。"""
        self.git.fetch(reuse=reuse)
        for branch in (name, into):
            if not self.git.has_remote_branch(branch):
                raise WorkError(ErrorCode.BRANCH_NOT_FOUND, f"GitHubにブランチ {branch} がありません。")
        return (self.git.output("rev-parse", f"{_git.REMOTE}/{name}"),
                self.git.output("rev-parse", f"{_git.REMOTE}/{into}"))

    def _branch_merge_tree(self, head: str, base: str) -> tuple[str, str, tuple[str, ...]]:
        """head を base へ合わせた結果（方法, マージコミットの tree, 衝突するファイル）。作業ツリーには触れない（merge-tree）。"""
        if self.git.is_ancestor(head, base):
            return "up-to-date", "", ()
        if self.git.is_ancestor(base, head):
            return "fast-forward", "", ()
        merged = self.git.run("merge-tree", "--write-tree", "--name-only", "--no-messages", base, head, check=False)
        lines = merged.stdout.splitlines()
        if merged.returncode == 1:
            return "conflict", "", tuple(line for line in lines[1:] if line)
        if not merged.ok or not lines:
            raise _git._git_error(merged)
        return "merge", lines[0], ()
