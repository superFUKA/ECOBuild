"""Repository の一部：タスクの管理とマイルストーン（ecotask に任せ、タスクブランチ・提出のことを足す）。

Repository（repository.py）がこのクラスを継承する。self は Repository。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ecotask import tracker as _tracker
from . import github as _github
from . import model as wm
from .errors import ErrorCode, WorkError


class TaskManagement:
    # タスクの管理（ecotask に任せ、タスクブランチ・PRのことを足す） -------------------------------

    def tasks(self, *, closed: bool = False, label: str | None = None, assignee: str | None = None,
              search: str | None = None, milestone: str | None = None, ready: bool = False,
              sort: str | None = None, sprint: str | None = None, submitted: bool = False,
              to_review: bool = False) -> list[wm.TaskSummary]:
        """タスクの一覧。label・assignee（@me は自分）・search（GitHubの検索の書き方）・milestone・sprint
        （スプリントの名前か current）で絞り込む。

        ready：着手できるタスクだけ（開いている・先に終わるべきタスクがない・親が待っていない・開いている子タスクがない・
        タスクブランチがまだない・未着手か段階が未設定のもの。計画中のものは除く）。
        sort：計画・記録の値で並べる（ecotask の Tracker.sort。priority・due 等）。
        submitted：提出中のものだけ。to_review：自分がレビューを頼まれている提出のものだけ。

        一覧のついでに、段階のずれ（GitHubのサイトでのマージ・閉じる等の分）を直す。
        """
        if sort is not None:
            self.tracker.sort([], sort)  # 一覧を取る前に、並べられるか確かめる
        # GitHub への問い合わせ（fetch・PRの一覧・タスクの一覧）は互いに関係ないので、並べて待つ
        with ThreadPoolExecutor(max_workers=3) as pool:
            fetching = pool.submit(self.git.fetch, reuse=True)
            opened = pool.submit(self.github.list_pull_requests, self.root, closed=False)
            reviewing = pool.submit(self.github.list_pull_requests, self.root, closed=False,
                                    review_requested="@me") if to_review else None
            tasks = self.tracker.tasks(closed=closed, label=label, assignee=assignee, search=search,
                                       milestone=milestone, sprint=sprint)
            waiting = set()   # 親が待っているタスク（絞り込んでいれば親が一覧にないことがあるので、取り直す）
            if ready:
                narrowed = label or assignee or search or milestone is not None or sprint is not None
                waiting = self.tracker.waiting_on_parent(None if narrowed else tasks)
            fetching.result()
            pulls = opened.result()
            wanted = None if reviewing is None else {wm.task_number(i.head) for i in reviewing.result()}
        local, remote = set(self.git.local_branches()), set(self.git.remote_branches())
        current = self.git.current_branch()
        pairs = []
        tasks = self.tracker.sync_stages(tasks, self._work_states(remote, pulls)) if self.tracker.board else tasks
        submissions = {}
        for info in sorted(pulls, key=lambda i: i.number):
            number = wm.task_number(info.head)
            if number is not None:
                submissions[number] = self._submission_state(info)
        branches = {}   # タスクの番号 → タスクブランチ（手元のものを先に）
        for name in sorted(remote) + sorted(local):
            number = wm.task_number(name)
            if number is not None:
                branches[number] = name
        for task in tasks:
            branch = branches.get(task.number, wm.task_branch_name(task.number))
            summary = wm.TaskSummary._from(task, task_branch=branch in local, current=branch == current,
                                           remote=branch in remote, path=self.root,
                                           submission=submissions.get(task.number), branch=branch)
            if ready and not (self.tracker.startable(task, waiting) and not (summary.task_branch or summary.remote)):
                continue
            if (submitted and summary.submission is None) or (wanted is not None and task.number not in wanted):
                continue
            pairs.append((summary, task))
        if sort is not None:
            pairs = self.tracker.sort(pairs, sort, task_of=lambda pair: pair[1])
        return [summary for summary, _ in pairs]

    def _current_work_states(self) -> dict[int, _tracker.WorkState]:
        """GitHubの最新を取得して、各タスクの作業の事実を調べる（判断の前に段階のずれを直すため）。"""
        self.git.fetch(reuse=True)
        return self._work_states(set(self.git.remote_branches()))

    def _work_states(self, remote: set[str], pulls: list | None = None) -> dict[int, _tracker.WorkState]:
        """各タスクの作業の事実（GitHubのタスクブランチのブランチ・開いているPR）。段階のずれを直すのに使う。
        pulls：開いているPRの一覧（読んであれば。なければ読む）。"""
        work = {}
        for branch in remote:
            number = wm.task_number(branch)
            if number is not None:
                work[number] = _tracker.WorkState(branch=True)
        for pull in self.github.list_pull_requests(self.root, closed=False) if pulls is None else pulls:
            number = wm.task_number(pull.head)
            if number is not None:
                work[number] = _tracker.WorkState(branch=True, pull_request=True, draft=pull.draft)
        return work

    def _task_branches(self) -> set[int]:
        """タスクブランチ（手元かGitHubにあるもの）のタスクの番号。"""
        self.git.fetch(reuse=True)
        names = set(self.git.local_branches()) | set(self.git.remote_branches())
        return {n for n in (wm.task_number(b) for b in names) if n is not None}

    def next_tasks(self, *, assignee: str | None = None, count: int | None = None) -> list:
        """次にやるもの（順位と理由。ecotask.planning.next_tasks）。タスクブランチがあるタスクは除く。"""
        ranked = self.tracker.next_tasks(assignee=assignee, exclude=self._task_branches())
        return ranked if count is None else ranked[:count]

    def deadlines(self, *, days: int = 3):
        return self.tracker.deadlines(days=days)

    def sprints(self) -> list:
        return self.tracker.sprints()

    def sprint_status(self, name: str = "current"):
        return self.tracker.sprint_status(name)

    def workload(self) -> list:
        return self.tracker.workload()

    def milestone_status(self) -> list:
        return self.tracker.milestone_status()

    def plan_task(self, number: int, **values) -> wm.TaskSummary:
        """計画の値（priority・due・estimate・sprint〔current 可〕・planned_start・planned_end・clear）と、
        作業を始める前の段階（stage：planned・todo）を設定する。"""
        task = self.tracker.plan(number, **values)
        branch = self._existing_task_branch(number)
        local = branch is not None and self.git.has_local_branch(branch)
        return wm.TaskSummary._from(task, task_branch=local, current=local and self.git.current_branch() == branch,
                                    remote=False, path=self.root, branch=branch)

    def task_status(self, number: int | None = None) -> wm.TaskStatus:
        """Issueと、タスクブランチ・PR（レビュー・コメント・CIの結果）の状態。省略時は今いるタスクブランチ。"""
        if number is None:
            number = self.require_task_branch("番号を省略したタスクの指定").number
        # Issue（GitHub）を読む間に、fetch と、タスクブランチが分かれば提出（PR）も読む
        with ThreadPoolExecutor(max_workers=2) as pool:
            reading = pool.submit(self.tracker.details, number)
            self.git.fetch(reuse=True)
            branch = self._existing_task_branch(number)
            submission = None if branch is None else pool.submit(self._latest_submission, branch)
            details = reading.result()
            if branch is None:   # 手元にも GitHub にもない：Issueに記録した名前（なければ決まりの名前）
                branch = wm.issue_branch(details.body) or wm.task_branch_name(number)
                latest, activity = self._latest_submission(branch)
            else:
                latest, activity = submission.result()
        task = details.task
        local = self.git.has_local_branch(branch)
        base = self.git.get_config(wm.base_key(branch)) or wm.issue_base(details.body)
        return wm.TaskStatus(
            number, task.title, task.state, task.url, wm.without_base(details.body), self.git.has_local_branch(branch),
            base,
            None if latest is None else self._submission_state(latest), activity,
            self.git.has_remote_branch(branch), task.labels, task.assignees, details.comments, task.milestone,
            details.parent, details.subtasks, details.blocked_by, details.blocking,
            wm.TaskSummary._from(task, task_branch=local, current=self.git.current_branch() == branch,
                                 remote=self.git.has_remote_branch(branch), path=self.root, branch=branch),
            self.root if local else None, self._task_commits(branch, base or self.default_base, local),
            branch if local or self.git.has_remote_branch(branch) else None)

    def _latest_submission(self, branch: str) -> tuple[_github.PullRequestInfo | None, _github.PullRequestActivity | None]:
        """branch の最新のPRと、そのレビュー・コメント・CIの結果（なければ None, None）。"""
        pulls = self.github.pull_requests_for_branch(self.root, branch)
        latest = max(pulls, key=lambda p: p.number) if pulls else None
        return latest, None if latest is None else self.github.pull_request_activity(self.root, latest.number)

    def _task_commits(self, branch: str, base: str, local: bool) -> tuple[str, ...]:
        """提出に入るコミット：タスクブランチ（手元、なければ GitHub のもの）にあって、作成元（GitHub のもの）にないもの。"""
        remote = f"origin/{branch}"
        head = branch if local else remote if self.git.rev_parse(remote) else None
        target = f"origin/{base}" if self.git.rev_parse(f"origin/{base}") else base if self.git.rev_parse(base) else None
        if head is None or target is None:
            return ()
        log = self.git.output("log", "--format=%h %s", f"{target}..{head}")
        return tuple(log.splitlines()) if log else ()

    def edit_task(self, number: int, *, body: str | None = None, **changes) -> wm.Task:
        """題名・本文・ラベル・担当者（@me は自分）・親タスク・先に終わるべきタスク・マイルストーンを変える
        （ecotask の Tracker.edit と同じ）。本文を変えても、作成元の記録（本文の末尾の印）は残す。"""
        if body is not None:
            recorded = wm.issue_base(self.tracker.issue(number).body)
            body = body if recorded is None else wm.with_base(body, recorded)
        self.tracker.edit(number, body=body, **changes)
        return self.task(number)

    def comment_task(self, number: int | None, body: str) -> wm.Task:
        """タスク（Issue）にコメントを残す（作業の記録・申し送り）。省略時は今いるタスクブランチのタスク。"""
        if not body.strip():
            raise WorkError(ErrorCode.INVALID_ARGUMENT, "コメントが空です。")
        if number is None:
            number = self.require_task_branch("番号を省略したタスクの指定").number
        self.tracker.comment(number, body)
        return self.task(number)

    def close_task(self, number: int, *, not_planned: bool = False) -> wm.Task:
        """Issueを閉じる。開いている子タスク、タスクブランチに開いているPRかマージしていないコミットがあれば止める。

        作業の終わり方は「task finish で完了する」か「task drop で捨てる」のどちらか（Issueだけ閉じると、
        タスクブランチの変更が宙に浮く）。
        """
        self.tracker.check_closable(number)
        self.git.fetch()
        branch = self._task_branch_of(number)
        local, remote = self.git.has_local_branch(branch), self.git.has_remote_branch(branch)
        if local or remote:
            self._guard_removal(branch, "タスクを閉じること", switching=False)   # ロック中のほかの作業空間が作業している
            base = self.git.get_config(wm.base_key(branch)) or self.default_base
            opened = [p.number for p in self.github.pull_requests_for_branch(self.root, branch) if p.state == "open"]
            lost = self._lost_commits(branch, base, local=local, remote=remote)
            if opened or lost:
                raise WorkError(
                    ErrorCode.UNFINISHED_WORK,
                    f"Issue #{number} のタスクブランチ {branch} に、" +
                    ("開いているPR（" + ", ".join(f"#{n}" for n in opened) + "）" if opened else "マージしていないコミット") +
                    "があります。",
                    hint=f"完了するなら {self._op('task finish')} {number}、やめるなら {self._op('task drop')} {number} "
                         "--close（または task close {number} --yes）で閉じてください。",
                    details=list(lost),
                )
        self.tracker.close(number, not_planned=not_planned)
        return self.task(number)

    def start_task_without_branch(self, number: int, *, ignore_blocked: bool = False,
                                     take_over: bool = False) -> wm.Task:
        """タスクブランチを作らずに作業を始める（調査・設計等、コードを変えないタスク）。担当者がいなければ自分にし、
        作業中にする。親タスク・依存待ち・担当者の確かめは task start と同じ。"""
        return wm.Task._from(self, self.tracker.start_without_branch(number, ignore_blocked=ignore_blocked,
                                                                          take_over=take_over))

    def reopen_task(self, number: int) -> wm.Task:
        self.tracker.reopen(number)
        return self.task(number)

    def prepare_tasks(self) -> None:
        """タスク管理の準備（ecotask の Tracker.prepare）。"""
        self.tracker.prepare()

    # マイルストーン（ecotask と同じ） ---------------------------------------------

    def milestones(self, *, closed: bool = False) -> list[_github.MilestoneInfo]:
        return self.tracker.milestones(closed=closed)

    def create_milestone(self, title: str, *, due: str | None = None, description: str = "") -> _github.MilestoneInfo:
        return self.tracker.create_milestone(title, due=due, description=description)

    def edit_milestone(self, title: str, **changes) -> _github.MilestoneInfo:
        return self.tracker.edit_milestone(title, **changes)
