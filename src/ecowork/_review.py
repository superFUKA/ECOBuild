"""Repository の一部：他人の提出の確認と、提出（PR）の処理（レビュー・変更・状態）。

Repository（repository.py）がこのクラスを継承する。self は Repository。
"""

from __future__ import annotations

from ecotask import board as _board
from . import git as _git
from . import model as wm
from .errors import ErrorCode, WorkError
from ._shared import _REVIEW_KEY, _REVIEW_RETURN_KEY


class Reviewing:
    # 他人のPRの確認 -----------------------------------------------------------------

    def review(self, number: int) -> wm.ReviewResult:
        """PRの内容を手元に取り出して確認する（切り離された状態。コミットはできない）。"""
        if self._dirty():
            raise WorkError(ErrorCode.DIRTY_WORKING_TREE, "未コミットの変更があるため、PRを取り出せません。",
                            hint=f"{self._op('task commit')} か {self._op('stash')} で片付けてから実行してください。")
        pr = self.github.get_pull_request(self.root, number)
        self.git.run("fetch", "--quiet", _git.REMOTE, f"pull/{number}/head")
        sha = self.git.output("rev-parse", "FETCH_HEAD")
        if self._reviewing() is None:
            self.git.set_config(_REVIEW_RETURN_KEY, self.git.current_branch() or self.default_base)
        self.git.run("switch", "--quiet", "--detach", sha)
        self.git.set_config(_REVIEW_KEY, str(number))
        return wm.ReviewResult(number, pr.head, sha, task=wm.task_number(pr.head))

    def end_review(self) -> wm.ReviewResult:
        number = self._reviewing()
        if number is None:
            raise WorkError(ErrorCode.INVALID_ARGUMENT, "確認中のPRはありません。",
                            hint=f"{self._op('task review')} <PRの番号> で確認を始めます。")
        if self._dirty():
            raise WorkError(ErrorCode.DIRTY_WORKING_TREE, "確認中に変更したファイルがあります。",
                            hint=f"{self._op('restore')} で戻してから実行してください。")
        back = self.git.get_config(_REVIEW_RETURN_KEY) or self.default_base
        sha = self.git.output("rev-parse", "HEAD")
        self.git.switch(back)
        self.git.unset_config(_REVIEW_KEY)
        self.git.unset_config(_REVIEW_RETURN_KEY)
        return wm.ReviewResult(number, "", sha, back, task=self._task_of_pull_request(number))

    def _task_of_pull_request(self, number: int) -> int | None:
        try:
            return wm.task_number(self.github.get_pull_request(self.root, number).head)
        except WorkError:
            return None

    # PRの処理（レビュー・変更・状態） ------------------------------------------------

    def pull_requests(self, *, closed: bool = False, review_requested: str | None = None) -> list[wm.PullRequest]:
        """PRの一覧（新しい順）。closed なら閉じた・マージ済みも。review_requested：レビューを頼まれている人（@me）。"""
        infos = self.github.list_pull_requests(self.root, closed=closed, review_requested=review_requested)
        return [wm.PullRequest._from(self, i) for i in sorted(infos, key=lambda i: i.number, reverse=True)]

    def pull_request_status(self, number: int | None = None) -> wm.PullRequestStatus:
        """PRの内容・レビュー・コメント・CIの結果・マージできるか。省略時は今のタスクブランチのPR。"""
        info = self.github.get_pull_request(self.root, self.pull_request(number).number)
        return wm.PullRequestStatus(info.number, info.title, info.url, info.state, info.head, info.base, info.author,
                                    info.draft, info.body, wm.task_number(info.head),
                                    self.github.pull_request_activity(self.root, info.number))

    def pull_request_diff(self, number: int | None = None) -> str:
        return self.github.pull_request_diff(self.root, self.pull_request(number).number)

    def comment_pull_request(self, number: int | None, body: str) -> wm.PullRequest:
        if not body.strip():
            raise WorkError(ErrorCode.INVALID_ARGUMENT, "コメントが空です。")
        pr = self.pull_request(number)
        self.github.comment_pull_request(self.root, pr.number, body)
        return pr

    def review_pull_request(self, number: int, event: str, body: str = "") -> wm.PullRequest:
        """レビューの結果を返す。event：approve（承認）・request_changes（修正依頼）・comment（コメント）。"""
        if event not in ("approve", "request_changes", "comment"):
            raise WorkError(ErrorCode.INVALID_ARGUMENT, f"レビューの種類 {event} はありません。")
        if event != "approve" and not body.strip():
            raise WorkError(ErrorCode.INVALID_ARGUMENT, "修正依頼・コメントには内容が必要です。",
                            hint="--message で内容を書いてください。")
        pr = self.pull_request(number)
        if pr.state != "open":
            raise WorkError(ErrorCode.PULL_REQUEST_NOT_OPEN, f"PR #{pr.number} は開いていません（{pr.state}）。")
        self.github.review_pull_request(self.root, pr.number, event=event, body=body)
        task = wm.task_number(pr.head)
        if event == "request_changes" and task is not None:
            self.tracker.set_stage(task, _board.IN_PROGRESS)  # 直すのは作成者。出し直し（task submit）でレビュー待ちに戻る
        return pr

    def edit_pull_request(self, number: int | None = None, *, title: str | None = None, body: str | None = None,
                          base: str | None = None, add_reviewers: tuple[str, ...] = (),
                          remove_reviewers: tuple[str, ...] = (), add_labels: tuple[str, ...] = (),
                          remove_labels: tuple[str, ...] = ()) -> wm.PullRequest:
        """PRの題名・本文・向き先・レビュアー・ラベルを変える。

        None は変えない。body="" で本文を消す。タスクブランチのPRでは、そのIssueとのつながり（本文の Closes／Refs #<番号>）を
        残す（新しい本文に書けば、それで通常の反映と途中の反映を切り替えられる）。向き先を変えたらタスクブランチの作成元も
        そろえる（途中で失敗しても、同じ向き先でもう一度実行すれば残りがそろう）。
        """
        if title is None and body is None and base is None and not (
                add_reviewers or remove_reviewers or add_labels or remove_labels):
            raise WorkError(ErrorCode.INVALID_ARGUMENT, "変更する内容がありません。")
        if title is not None and not title.strip():
            raise WorkError(ErrorCode.INVALID_ARGUMENT, "PRの題名は空にできません。")
        pr = self.pull_request(number)
        task = wm.task_number(pr.head)
        if body is not None and task is not None:
            current = self.github.get_pull_request(self.root, pr.number)
            body = wm.with_task_link(body, task, partial=wm.PullRequest._from(self, current).partial)
        if base is not None:
            if wm.is_task_branch(base):
                raise WorkError(ErrorCode.INVALID_BASE, f"タスクブランチ {base} は向き先にできません。")
            self.git.fetch()
            if not self.git.has_remote_branch(base):
                raise WorkError(ErrorCode.BRANCH_NOT_FOUND, f"GitHubにブランチ {base} がありません。")
        self.github.edit_pull_request(self.root, pr.number, title=title, body=body, base=base,
                                      add_reviewers=add_reviewers, remove_reviewers=remove_reviewers,
                                      add_labels=add_labels, remove_labels=remove_labels)
        if base is not None and task is not None:
            if self.git.has_local_branch(pr.head):
                self.git.set_config(wm.base_key(pr.head), base)
            self._record_base(task, base)
        return self.pull_request(pr.number)

    def close_pull_request(self, number: int | None = None) -> wm.PullRequest:
        """PRを閉じる（ブランチ・タスクブランチ・Issueはそのまま。作業をやめるなら task drop）。"""
        pr = self.pull_request(number)
        if pr.state != "open":
            raise WorkError(ErrorCode.PULL_REQUEST_NOT_OPEN, f"PR #{pr.number} は開いていません（{pr.state}）。")
        self.github.close_pull_request(self.root, pr.number)
        task = wm.task_number(pr.head)
        if task is not None:
            self.tracker.set_stage(task, _board.IN_PROGRESS)  # タスクブランチは残っている（やめるなら task drop）
        return self.pull_request(pr.number)

    def reopen_pull_request(self, number: int) -> wm.PullRequest:
        pr = self.pull_request(number)
        if pr.state != "closed":
            raise WorkError(ErrorCode.INVALID_ARGUMENT, f"PR #{pr.number} は閉じていません（{pr.state}）。")
        self.github.reopen_pull_request(self.root, pr.number)
        task = wm.task_number(pr.head)
        if task is not None:
            self.tracker.set_stage(task, _board.IN_PROGRESS if pr.draft else _board.IN_REVIEW)
        return self.pull_request(pr.number)

    def set_pull_request_draft(self, number: int | None = None, *, draft: bool) -> wm.PullRequest:
        """下書きにする（draft=True）・下書きを解除してレビューを頼める状態にする（False）。"""
        pr = self.pull_request(number)
        if pr.state != "open":
            raise WorkError(ErrorCode.PULL_REQUEST_NOT_OPEN, f"PR #{pr.number} は開いていません（{pr.state}）。")
        if pr.draft != draft:
            self.github.set_pull_request_draft(self.root, pr.number, draft)
        task = wm.task_number(pr.head)
        if task is not None:
            self.tracker.set_stage(task, _board.IN_PROGRESS if draft else _board.IN_REVIEW)
        return self.pull_request(pr.number)

    def remove_task_branch(self, number: int | None = None) -> wm.RemoveResult:
        """手元のタスクブランチだけを消す。GitHubのブランチ・PR・Issueはそのまま。

        タスクブランチの本体はGitHub（Issue・ブランチ・PR）にあり、手元はその写し。task start で、pushした所から
        同じ作成元で再開できる。GitHubにないもの（未コミットの変更・未pushのコミット）があれば止める。
        """
        if number is None:
            number = self.require_task_branch("番号を省略したタスクブランチの指定").number
        branch = wm.task_branch_name(number)
        if not self.git.has_local_branch(branch):
            raise WorkError(ErrorCode.BRANCH_NOT_FOUND, f"手元にタスクブランチ {branch} はありません。")
        current = self.git.current_branch() == branch
        if current and self._dirty():
            raise WorkError(ErrorCode.DIRTY_WORKING_TREE, "未コミットの変更があるため、手元のタスクブランチを消せません。",
                            hint=f"{self._op('task commit')} と {self._op('task push')} でGitHubへ送るか、"
                                 f"{self._op('restore')} で戻してから実行してください。")
        self.git.fetch()
        remote = self.git.has_remote_branch(branch)
        base = self.git.get_config(wm.base_key(branch)) or self.default_base
        if remote:
            unpushed = tuple(self.git.output("log", "--format=%s", branch, "--not",
                                             f"{_git.REMOTE}/{branch}").splitlines())
        else:
            unpushed = self._lost_commits(branch, base, local=True, remote=False)
        if unpushed:
            raise WorkError(ErrorCode.COMMITS_WOULD_BE_LOST,
                            f"タスクブランチ {branch} に、GitHubにないコミットが {len(unpushed)} 件あります。",
                            hint=f"{self._op('task push')} でGitHubへ送ってから実行してください"
                                 f"（作業をやめるなら {self._op('task drop')} {number}）。",
                            details=list(unpushed))
        self._record_base(number, base)
        switched_to = None
        if current:
            switched_to = base
            self._switch_to_latest(base)
        self.git.delete_branch(branch, force=True)
        self.git.unset_config(wm.base_key(branch))
        return wm.RemoveResult(number, branch, base, remote, switched_to)

    def _recorded_base(self, number: int, branch: str) -> str | None:
        """GitHubに残した作成元：開いているPRの向き先、なければIssueの本文の印。"""
        opened = [p for p in self.github.pull_requests_for_branch(self.root, branch) if p.state == "open"]
        if opened:
            return max(opened, key=lambda p: p.number).base
        return wm.issue_base(self.github.get_issue(self.root, number).body)

    def _record_base(self, number: int, base: str, *, claim: bool = False) -> None:
        """作成元をIssueの本文に記録する（手元のタスクブランチを消しても、同じ作成元で再開できるように）。

        claim：担当者がいなければ自分を担当者にする（誰が作業しているかをGitHubで分かるように）。
        """
        issue = self.github.get_issue(self.root, number)
        body = None if wm.issue_base(issue.body) == base else wm.with_base(issue.body, base)
        assignees = ("@me",) if claim and not issue.assignees else ()
        if body is not None or assignees:
            self.github.edit_issue(self.root, number, body=body, add_assignees=assignees)

    def prune_task_branch(self, number: int) -> wm.CleanResult | wm.RemoveResult:
        """1つのタスクブランチを片付ける：タスクが閉じていれば片付け（prune_task_branches と同じ）、開いていれば手元の写しだけを
        消す（remove_task_branch と同じ。GitHubのブランチ・提出は残り、task start で再開できる）。"""
        if self.github.get_issue(self.root, number).state == "open":
            return self.remove_task_branch(number)
        result = self.prune_task_branches(only=number)
        if not (result.removed or result.skipped):
            raise WorkError(ErrorCode.BRANCH_NOT_FOUND, f"手元にタスクブランチ {wm.task_branch_name(number)} はありません。")
        return result

    def prune_task_branches(self, *, dry_run: bool = False, only: int | None = None) -> wm.CleanResult:
        """Issueが閉じたタスクブランチのブランチを片付ける。未pushの変更があるタスクブランチは残す。only：その番号のタスクブランチだけ。"""
        self.git.fetch()
        current = self.git.current_branch()
        removed, skipped, switched_to = [], [], None
        for branch in self.git.local_branches():
            number = wm.task_number(branch)
            if number is None or (only is not None and number != only):
                continue
            try:
                issue = self.github.get_issue(self.root, number)
            except WorkError:
                skipped.append(wm.SkippedBranch(branch, "Issueを取得できません"))
                continue
            if issue.state != "closed":
                continue
            reason = self._unsafe_to_remove(branch)
            if reason is None and branch == current:
                tree = self.git.working_tree()
                if tree.staged or tree.unstaged or tree.conflicted:
                    reason = "今いるタスクブランチに未コミットの変更があります"
            if reason is not None:
                skipped.append(wm.SkippedBranch(branch, reason))
                continue
            if dry_run:
                removed.append(branch)
                continue
            if branch == current:
                switched_to = self.git.get_config(wm.base_key(branch)) or self.default_base
                self._switch_to_latest(switched_to)
            self.git.delete_branch(branch, force=True)
            if self.git.has_remote_branch(branch):
                self.git.push_delete(branch)
            self.git.unset_config(wm.base_key(branch))
            removed.append(branch)
        return wm.CleanResult(tuple(removed), tuple(skipped), switched_to, dry_run)

    def drop_task(self, number: int | None = None, *, close: bool = False, discard: bool = False,
                       dry_run: bool = False) -> wm.DropResult:
        """PRを出さずに作業をやめる：開いているPRを閉じ、タスクブランチを手元とGitHubから消す。

        numberを省略すると今いるタスクブランチ。今いるタスクブランチなら作成元へ移って最新にする。
        Issueは既定で開いたまま（後で task start で最初からやり直せる）。closeで「対応しない」として閉じる。
        開いている子タスクがあれば止める（子のタスクブランチは親のタスクブランチから派生しているため）。
        作成元に入っていないコミットは失われるため、discardがなければ止める。
        dry_runは何もせず、行う内容（失われるコミット等）を返す。
        """
        if number is None:
            task_branch = self.require_task_branch("作業の中断")
            number, branch = task_branch.number, task_branch.branch
        else:
            branch = wm.task_branch_name(number)
        # 子タスクのタスクブランチは親のタスクブランチから派生する：親のタスクブランチを消す・閉じるのは子が終わってから
        self.tracker.check_finishable(number, action="作業をやめることは")
        current = self.git.current_branch()
        if current == branch and self._dirty():
            raise WorkError(
                ErrorCode.DIRTY_WORKING_TREE,
                "未コミットの変更があるため、タスクブランチを捨てられません。",
                hint=f"残す変更は {self._op('task commit')} か {self._op('stash')}、"
                     f"捨てる変更は {self._op('restore')} で片付けてから実行してください。",
            )
        self.git.fetch()
        local, remote = self.git.has_local_branch(branch), self.git.has_remote_branch(branch)
        if not (local or remote):
            if close:
                # 開始していない（タスクブランチのない）Issueを「対応しない」として閉じる。
                if not dry_run and self.github.get_issue(self.root, number).state == "open":
                    self.github.close_issue(self.root, number, not_planned=True)
                    self.tracker.closed(number)
                return wm.DropResult(number, branch, (), (), None, close, dry_run)
            raise WorkError(ErrorCode.BRANCH_NOT_FOUND, f"タスクブランチ {branch} がありません。",
                            hint="開始していないIssueをやめる場合は --close を付けてください（「対応しない」として閉じます）。")
        base = self.git.get_config(wm.base_key(branch)) or self.default_base
        lost = self._lost_commits(branch, base, local=local, remote=remote)
        pulls = tuple(p.number for p in self.github.pull_requests_for_branch(self.root, branch) if p.state == "open")
        switched_to = base if current == branch else None
        if dry_run:
            return wm.DropResult(number, branch, lost, pulls, switched_to, close, True)
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
        self.git.unset_config(wm.base_key(branch))
        if close and self.github.get_issue(self.root, number).state == "open":
            self.github.close_issue(self.root, number, not_planned=True)
            self.tracker.closed(number)
        elif not close:
            self.tracker.set_stage(number, _board.TODO)  # Issueは開いたまま：最初からやり直せる
        return wm.DropResult(number, branch, lost, pulls, switched_to, close, False)
