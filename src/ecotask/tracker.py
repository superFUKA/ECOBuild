"""タスク管理の操作と決まりごと。データはすべてGitHubに置く（保存の層：ecotask.store）。

作業空間やPRのことは知らない。作業の流れ（ecowork）は、作業の段階が変わるときに set_stage を呼び、
段階のずれを直すとき（sync_stages）は各タスクの作業の事実（開いているPR・作業空間の有無）を渡す。
計画の情報を置くボードは内部の保存場所で、利用者には見せない（ecotask.board）。
判断（次にやるもの・期限・スプリント等）は ecotask.planning の関数で行う。
"""

from __future__ import annotations

import datetime as _datetime
from dataclasses import dataclass, replace
from pathlib import Path

from . import board as _board
from . import github as _github
from . import model as _model
from . import planning as _planning
from .errors import ErrorCode, TaskError, operation
from .store import TaskStore


@dataclass(frozen=True)
class TaskRef:
    """他のタスク（親子・依存の相手）。"""
    number: int
    title: str
    state: str

    @classmethod
    def _from(cls, info: _github.IssueInfo) -> "TaskRef":
        return cls(info.number, info.title, info.state)


@dataclass(frozen=True)
class TaskDetails:
    """1件の詳細：タスク・本文・コメント・親・子・先に終わるべきタスク・待っているタスク。"""
    task: _model.Task
    body: str
    comments: tuple[_github.Comment, ...]
    parent: TaskRef | None
    subtasks: tuple[TaskRef, ...]
    blocked_by: tuple[TaskRef, ...]
    blocking: tuple[TaskRef, ...]


@dataclass(frozen=True)
class WorkState:
    """段階のずれを直すときの、タスクの作業の事実（作業の流れの側が調べて渡す）。"""
    branch: bool = False                                 # 作業空間（GitHubのブランチ）がある
    pull_request: bool = False                           # 開いているPRがある
    draft: bool = False                                  # そのPRが下書き


# task list --sort で並べられるもの
SORT_KEYS = (*_model.ROLES, "created", "finished")


class Tracker:
    def __init__(self, root: Path | str, *, github: _github.TaskGitHub | None = None, command: str = "",
                 legacy_board: str | None = None):
        """
        root：GitHubのリポジトリを決める手元のclone（gh はその origin を使う）。
        command：ヒントに書くCLIのコマンド名。
        legacy_board：以前の設定でつないでいたボードのURL（あれば、計画の情報の置き場所として引き継ぐ）。
        """
        self.root = Path(root)
        self.store = TaskStore(self.root, github if github is not None else _github.GhCli(), legacy_board)
        self.command = command
        # 操作は成功したが、知らせておくこと（親タスクの子がすべて閉じた等）
        self.notices: list[str] = []

    @property
    def github(self) -> _github.TaskGitHub:
        return self.store.github

    @github.setter
    def github(self, value: _github.TaskGitHub) -> None:
        self.store.github = value

    @property
    def board(self) -> _board.BoardSettings | None:
        """計画の情報を置くボード（内部）。なければNone。"""
        return self.store.board

    # タスク（Issue） ------------------------------------------------------------------

    def issue(self, number: int) -> _github.IssueInfo:
        return self.github.get_issue(self.root, number)

    def task(self, number: int) -> _model.Task:
        return self.store.task(number)

    def create(self, title: str, *, body: str = "", labels: tuple[str, ...] = (), assignees: tuple[str, ...] = (),
               parent: int | None = None, blocked_by: tuple[int, ...] = (),
               milestone: str | None = None, plan: dict[str, str | None] | None = None) -> _github.IssueInfo:
        """タスクを作り、未着手にする。parent：親、blocked_by：先に終わるべきタスク。
        plan：計画の値（役割 → 値。期限・開始予定日・終了予定日等。ecotask.store の plan と同じ）。"""
        if milestone is not None:
            self.milestone_number(milestone)  # 作る前に確かめる
        plan = {role: value for role, value in (plan or {}).items() if value is not None}
        if plan:
            self.store.prepare(plan)
        info = self.github.create_issue(self.root, title, body, labels=labels, assignees=assignees)
        self.set_stage(info.number, _model.TODO)
        if parent is None and not blocked_by and milestone is None and not plan:
            return info
        try:
            self.set_relations(info.number, parent=parent, add_blocked_by=blocked_by, milestone=milestone)
            if plan:
                self.store.plan(info.number, **plan)
        except TaskError as error:
            error.hint = ((error.hint + "\n") if error.hint else "") + (
                f"Issue #{info.number} は作成済みです。{self._op('task edit')} {info.number} で設定し直してください。")
            raise
        return self.issue(info.number)

    def edit(self, number: int, *, title: str | None = None, body: str | None = None,
             add_labels: tuple[str, ...] = (), remove_labels: tuple[str, ...] = (),
             add_assignees: tuple[str, ...] = (), remove_assignees: tuple[str, ...] = (),
             parent: int | None = None, clear_parent: bool = False, add_blocked_by: tuple[int, ...] = (),
             remove_blocked_by: tuple[int, ...] = (), milestone: str | None = None,
             clear_milestone: bool = False, plan: dict[str, str | None] | None = None,
             clear_plan: tuple[str, ...] = ()) -> _github.IssueInfo:
        """題名・本文・ラベル・担当者（@me は自分）・親・先に終わるべきタスク・マイルストーン、
        計画の値（plan：役割 → 値、clear_plan：消す役割。ecotask.store の plan と同じ）を変える。"""
        plan = {role: value for role, value in (plan or {}).items() if value is not None}
        if title is None and body is None and parent is None and milestone is None and not (
                add_labels or remove_labels or add_assignees or remove_assignees or clear_parent
                or add_blocked_by or remove_blocked_by or clear_milestone or plan or clear_plan):
            raise TaskError(ErrorCode.INVALID_ARGUMENT, "変更する内容がありません。",
                            hint="題名・本文・ラベル・担当者・親・依存・マイルストーン・計画の値のどれかを指定してください。")
        if plan or clear_plan:
            self.store.prepare(plan, clear_plan, self.task(number))   # 他を変える前に確かめる
        if parent is not None and clear_parent:
            raise TaskError(ErrorCode.INVALID_ARGUMENT, "親の指定と解除は同時にできません。")
        if milestone is not None and clear_milestone:
            raise TaskError(ErrorCode.INVALID_ARGUMENT, "マイルストーンの指定と解除は同時にできません。")
        if title is not None or body is not None or add_labels or remove_labels or add_assignees or remove_assignees:
            self.github.edit_issue(self.root, number, title=title, body=body, add_labels=add_labels,
                                   remove_labels=remove_labels, add_assignees=add_assignees,
                                   remove_assignees=remove_assignees)
        self.set_relations(number, parent=parent, clear_parent=clear_parent, add_blocked_by=add_blocked_by,
                           remove_blocked_by=remove_blocked_by, milestone=milestone, clear_milestone=clear_milestone)
        if plan or clear_plan:
            self.store.plan(number, clear=clear_plan, **plan)
        return self.issue(number)

    def set_relations(self, number: int, *, parent: int | None = None, clear_parent: bool = False,
                      add_blocked_by: tuple[int, ...] = (), remove_blocked_by: tuple[int, ...] = (),
                      milestone: str | None = None, clear_milestone: bool = False) -> None:
        """親子・依存・マイルストーンを設定する。別の親からの付け替えは暗黙に行わない。"""
        for other in (parent, *add_blocked_by):
            if other == number:
                raise TaskError(ErrorCode.INVALID_ARGUMENT, f"#{number} 自身は指定できません。")
        if parent is not None or clear_parent:
            current = self.github.issue_relation(self.root, number).parent
            if parent is not None and current not in (None, parent):
                raise TaskError(ErrorCode.INVALID_ARGUMENT, f"#{number} には既に親 #{current} があります。",
                                hint=f"付け替えるなら、先に {self._op('task edit')} {number} --clear-parent で外してください。")
            if clear_parent and current is not None:
                self.github.remove_sub_issue(self.root, current, number)
            if parent is not None and current is None:
                self.github.add_sub_issue(self.root, parent, number)
        for other in add_blocked_by:
            self.github.add_blocked_by(self.root, number, other)
        for other in remove_blocked_by:
            self.github.remove_blocked_by(self.root, number, other)
        if milestone is not None or clear_milestone:
            self.github.set_issue_milestone(self.root, number,
                                            None if clear_milestone else self.milestone_number(milestone))

    def plan(self, number: int, *, stage: str | None = None, **values) -> _model.Task:
        """計画の値（priority・due・estimate・sprint〔名前か current〕・planned_start・planned_end・clear）を
        設定する（ecotask.store と同じ）。stage：作業を始める前の段階（planned：計画中、todo：未着手）。"""
        if stage is not None:
            self._check_planning_stage(number, stage)   # 他を書く前に確かめる
        given = values.get("clear") or any(v is not None for k, v in values.items() if k != "clear")
        written = self.store.plan(number, **values) if given or stage is None else {}
        task = self.store.apply(self.task(number), written)
        if stage is not None:
            settings = self.store.ensure()
            option = settings.planned if stage == _model.PLANNED else settings.option(_model.TODO)
            self.store.write(self.store.item(number), self.store.info().field(settings.status_field), option)
            task = replace(task, status=option, stage=stage, on_board=True)
        self._shared()
        return task

    def _check_planning_stage(self, number: int, stage: str) -> None:
        if stage not in (_model.PLANNED, _model.TODO):
            raise TaskError(ErrorCode.INVALID_ARGUMENT, f"段階 {stage} は設定できません。",
                            hint="planned（計画中）か todo（未着手）を指定してください。作業中・レビュー待ち・完了は、"
                                 f"{self._op('task start')}・{self._op('task submit')}・{self._op('task merge')} 等で変わります。")
        task = self.task(number)
        if not task.open:
            raise TaskError(ErrorCode.TASK_CLOSED, f"#{number} は閉じています。")
        if task.stage not in (None, _model.TODO, _model.PLANNED):
            raise TaskError(ErrorCode.INVALID_ARGUMENT, f"#{number} は作業を始めているため、計画中・未着手にできません。",
                            hint=f"作業をやめるなら {self._op('task drop')} {number}（未着手に戻ります）。")
        if stage == _model.PLANNED and self.store.ensure().planned is None:
            raise TaskError(ErrorCode.FIELD_NOT_FOUND, "GitHubのタスク管理の情報に、計画中の段階がありません。",
                            hint="GitHubで直接変えた場合は、Status の選択肢 Backlog を戻してください。")

    def comment(self, number: int, body: str) -> None:
        if not body.strip():
            raise TaskError(ErrorCode.INVALID_ARGUMENT, "コメントが空です。")
        self.github.comment_issue(self.root, number, body)

    def check_closable(self, number: int) -> None:
        """閉じてよいか：開いていて、開いている子タスクがない（親は子を終えてから閉じる）。"""
        if self.issue(number).state != "open":
            raise TaskError(ErrorCode.TASK_CLOSED, f"Issue #{number} は既に閉じています。")
        self.check_finishable(number)

    def check_finishable(self, number: int, *, action: str = "終了") -> None:
        """親タスクを終えてよいか：開いている子タスクがない（子が終わらないと親は終了できない）。
        閉じる・最後のPRのマージ・作業をやめる前に確かめる。action：止める操作の名前（メッセージ用）。"""
        opened = self._open_subtasks(number)
        if opened:
            raise TaskError(ErrorCode.OPEN_SUBTASKS,
                            f"#{number} には開いている子タスクがあるため、{action}できません。",
                            hint="子タスクを先に終えるか閉じてください（親子をやめるなら "
                                 f"{self._op('task edit')} <子の番号> --clear-parent）。",
                            details=[f"#{s.number} {s.title}" for s in opened])

    def close(self, number: int, *, not_planned: bool = False) -> None:
        """閉じて完了にする（確かめは check_closable）。親の子がすべて閉じたら知らせる。"""
        self.github.close_issue(self.root, number, not_planned=not_planned)
        self.closed(number)

    def closed(self, number: int) -> None:
        """タスクが閉じた後（PRのマージで閉じた場合も）：完了にし、親の子がすべて閉じたら知らせる。"""
        self.set_stage(number, _model.DONE)
        try:
            parent = self.github.issue_relation(self.root, number).parent
            if parent is None:
                return
            subtasks = self.github.sub_issues(self.root, parent)
            if subtasks and all(s.state == "closed" or s.number == number for s in subtasks):
                self.notices.append(f"親タスク #{parent} の子タスクはすべて閉じました。親も終えられます"
                                    f"（作業空間があれば {self._op('task submit')}・{self._op('task merge')}、"
                                    f"なければ {self._op('task close')} {parent}）。")
        except TaskError:
            pass  # 知らせるだけなので、失敗しても操作は成功のまま

    def reopen(self, number: int) -> None:
        if self.issue(number).state == "open":
            raise TaskError(ErrorCode.INVALID_ARGUMENT, f"Issue #{number} は開いています。")
        self.github.reopen_issue(self.root, number)
        self.set_stage(number, _model.TODO)

    def check_startable(self, number: int, *, ignore_blocked: bool = False) -> None:
        """新しく作業を始めてよいか：先に終わるべきタスクを待つ（親タスクも作業できる。子の作業空間は親の
        作業空間から派生し、子が終わるまで親は終了できない）。"""
        if ignore_blocked:
            return
        blockers = sorted((b for b in self.github.blocked_by(self.root, number) if b.state == "open"),
                          key=lambda b: b.number)
        if blockers:
            raise TaskError(ErrorCode.TASK_BLOCKED, f"#{number} は、先に終わるべきタスクを待っています。",
                            hint="先にそちらを終えてください。待たずに始めるなら --ignore-blocked。",
                            details=[f"#{b.number} {b.title}" for b in blockers])

    def start_without_workspace(self, number: int, *, ignore_blocked: bool = False) -> _github.IssueInfo:
        """作業空間を作らずに作業を始める（調査・設計等）。担当者がいなければ自分にし、作業中にする。"""
        issue = self.issue(number)
        if issue.state != "open":
            raise TaskError(ErrorCode.TASK_CLOSED, f"Issue #{number} は閉じています。")
        self.check_startable(number, ignore_blocked=ignore_blocked)
        if not issue.assignees:
            self.github.edit_issue(self.root, number, add_assignees=("@me",))
        self.set_stage(number, _model.IN_PROGRESS)
        return self.issue(number)

    # 一覧・詳細・判断 -----------------------------------------------------------------

    def tasks(self, *, closed: bool = False, label: str | None = None, assignee: str | None = None,
              search: str | None = None, milestone: str | None = None,
              sprint: str | None = None) -> list[_model.Task]:
        """タスクの一覧（番号の順）。sprint：スプリントの名前か current（今日を含むもの）。

        label・assignee（@me は自分）・search（GitHubの検索の書き方）はGitHubで絞り込む。
        """
        chosen = None if sprint is None else self.sprint(sprint)
        tasks = self.store.tasks(closed=closed)
        if label or assignee or search:
            numbers = {i.number for i in self.github.list_issues(self.root, closed=closed, label=label,
                                                                 assignee=assignee, search=search)}
            tasks = [t for t in tasks if t.number in numbers]
        if milestone is not None:
            tasks = [t for t in tasks if t.milestone == milestone]
        if chosen is not None:
            tasks = [t for t in tasks if t.sprint == chosen]
        return tasks

    def startable(self, task: _model.Task) -> bool:
        return _planning.startable(task)

    def sort(self, tasks: list, name: str, *, task_of=lambda item: item) -> list:
        """計画・記録の値（SORT_KEYS：priority・due・…）で並べる。優先度・スプリントは順位・始まりの順、日付・
        見積もりは小さい順。値のないものは後ろ。task_of：要素から Task を取り出す関数（既定は要素そのもの）。"""
        if name not in SORT_KEYS:
            raise TaskError(ErrorCode.INVALID_ARGUMENT, f"{name} では並べられません。",
                            hint=f"{'・'.join(SORT_KEYS)} のどれかを指定してください。")
        pick = {_model.PRIORITY: lambda t: t.priority_rank, _model.ESTIMATE: lambda t: t.estimate,
                _model.SPRINT: lambda t: None if t.sprint is None else t.sprint.start}.get(
            name, lambda t: getattr(t, name))   # 日付は Task の同じ名前の属性
        return sorted(tasks, key=lambda item: _missing_last(pick(task_of(item)), task_of(item).number))

    def details(self, number: int) -> TaskDetails:
        task = self.store.task(number)

        def refs(infos):
            return tuple(TaskRef._from(i) for i in sorted(infos, key=lambda i: i.number))

        parent = None if task.parent is None else TaskRef._from(self.issue(task.parent))
        return TaskDetails(task, self.issue(number).body, tuple(self.github.issue_comments(self.root, number)), parent,
                           refs(self.github.sub_issues(self.root, number)),
                           refs(self.github.blocked_by(self.root, number)),
                           refs(self.github.blocking(self.root, number)))

    def next_tasks(self, *, assignee: str | None = None, exclude: set[int] = frozenset(),
                   today: _datetime.date | None = None) -> list[_planning.NextTask]:
        """次にやるもの（順位と理由。ecotask.planning.next_tasks）。exclude：除くタスク（作業空間があるもの等）。"""
        today = today or _datetime.date.today()
        tasks = self.tasks(assignee=assignee) if assignee else self.store.tasks()
        return _planning.next_tasks(tasks, today, sprints=self.sprints(), exclude=exclude)

    def deadlines(self, *, days: int = 3, today: _datetime.date | None = None) -> _planning.Deadlines:
        return _planning.deadlines(self.store.tasks(), today or _datetime.date.today(), days=days)

    def sprints(self) -> list[_model.Sprint]:
        return self.store.sprints()

    def sprint(self, name: str, *, today: _datetime.date | None = None) -> _model.Sprint:
        """スプリントを名前で探す（大文字・小文字は区別しない）。current は今日を含むもの。"""
        sprints = self.store.sprints()
        if not sprints:
            raise TaskError(ErrorCode.INVALID_ARGUMENT, "スプリントがまだありません。",
                            hint=f"{self._op('task plan')} でタスクの計画を初めて設定すると、今週から2週間ずつ3回分の"
                                 "スプリントができます。")
        today = today or _datetime.date.today()
        if name == "current":
            found = next((s for s in sprints if s.contains(today)), None)
            if found is None:
                raise TaskError(ErrorCode.INVALID_ARGUMENT, f"今日（{today.isoformat()}）を含むスプリントがありません。",
                                details=[f"{s.name} {s.start}〜{s.end}" for s in sprints])
            return found
        found = next((s for s in sprints if s.name.casefold() == name.casefold()), None)
        if found is None:
            raise TaskError(ErrorCode.INVALID_ARGUMENT, f"スプリント {name} はありません。",
                            details=[s.name for s in sprints])
        return found

    def sprint_status(self, name: str = "current", *, today: _datetime.date | None = None) -> _planning.SprintSummary:
        today = today or _datetime.date.today()
        return _planning.sprint_summary(self.store.tasks(closed=True), self.sprint(name, today=today), today)

    def workload(self, *, today: _datetime.date | None = None) -> list[_planning.Workload]:
        return _planning.workload(self.store.tasks(), today or _datetime.date.today())

    def milestone_status(self, *, today: _datetime.date | None = None) -> list[_planning.MilestoneSummary]:
        return _planning.milestone_summaries(self.store.tasks(closed=True), today or _datetime.date.today())

    # マイルストーン（リリースの目標と期日） ---------------------------------------------

    def milestones(self, *, closed: bool = False) -> list[_github.MilestoneInfo]:
        return self.github.list_milestones(self.root, closed=closed)

    def create_milestone(self, title: str, *, due: str | None = None, description: str = "") -> _github.MilestoneInfo:
        if not title.strip():
            raise TaskError(ErrorCode.INVALID_ARGUMENT, "マイルストーンの題名が必要です。")
        if any(m.title == title for m in self.milestones(closed=True)):
            raise TaskError(ErrorCode.ALREADY_EXISTS, f"マイルストーン {title} は既にあります。")
        return self.github.create_milestone(self.root, title, due=due, description=description)

    def edit_milestone(self, title: str, *, new_title: str | None = None, due: str | None = None,
                       description: str | None = None, state: str | None = None) -> _github.MilestoneInfo:
        """due="" で期日を消す。state：open／closed。"""
        if new_title is None and due is None and description is None and state is None:
            raise TaskError(ErrorCode.INVALID_ARGUMENT, "変更する内容がありません。")
        return self.github.edit_milestone(self.root, self.milestone_number(title), title=new_title, due=due,
                                          description=description, state=state)

    def milestone_number(self, title: str) -> int:
        for m in self.milestones(closed=True):
            if m.title == title:
                return m.number
        raise TaskError(ErrorCode.MILESTONE_NOT_FOUND, f"マイルストーン {title} がありません。",
                        hint=f"{self._op('milestone list')} --all で一覧、{self._op('milestone create')} で作成できます。")

    # 作業の段階（内部ではボードの状態） ---------------------------------------------------

    def prepare(self) -> None:
        """タスク管理の準備：計画・段階の置き場所（ボード）を作る（あれば足りない項目を足す）。モジュールを作るときに使う。"""
        self.store.ensure()
        self._shared()

    def set_stage(self, number: int, stage: str) -> None:
        """作業の段階を記録する。作業中・レビュー待ちなら、開始日がまだなければ今日にし、
        未着手・計画中の親も作業中にする（親の開始日も同じ）。置き場所（ボード）がなければ作る。

        失敗しても操作は成功のまま、知らせる（ずれは次の task list で直る）。
        """
        try:
            settings = self.store.ensure()
            option = settings.option(stage)
            status = self.store.info().field(settings.status_field)
            item = self.store.item(number)
            if item.values.get(status.name) != option:
                self.store.write(item, status, option)
            if stage in (_model.IN_PROGRESS, _model.IN_REVIEW):
                self.store.record_started(item)
                parent = self.github.issue_relation(self.root, number).parent
                if parent is not None:
                    parent_item = self.store.item(parent)
                    if self._parent_follows(parent_item.values.get(status.name)):
                        self.store.write(parent_item, status, settings.option(_model.IN_PROGRESS))
                        self.store.record_started(parent_item)
            self._shared()
        except TaskError as error:
            self.notices.append(f"#{number} の段階を GitHub に記録できませんでした（{error.message}）。"
                                f"次に {self._op('task list')} を実行すると合わせます。")

    def sync_stages(self, tasks: list[_model.Task], work: dict[int, WorkState]) -> list[_model.Task]:
        """段階のずれを直す（GitHubのサイトでの操作・失敗した記録の分）：段階を作業の事実（Issueの開閉と、
        work：作業空間・PR）に合わせ、子が始まった親は作業中にする。計画の段階・作業空間のない作業中は変えない。
        置き場所（ボード）がまだなければ何もしない。直した段階を重ねた tasks を返す。"""
        settings = self.board
        if settings is None or not tasks:
            return tasks
        by_number = {t.number: t for t in tasks}
        targets = {}
        for t in tasks:
            stage = self._expected_stage(t.state, t.status, work.get(t.number, WorkState()))
            targets[t.number] = None if stage is None else settings.option(stage)
        started = {settings.option(s) for s in (_model.IN_PROGRESS, _model.IN_REVIEW, _model.DONE)}
        for t in tasks:  # 子が始まった（作業中・レビュー待ち・完了）親は作業中
            parent = by_number.get(t.parent) if t.parent is not None else None
            if parent is not None and parent.open and (targets[t.number] or t.status) in started:
                if self._parent_follows(targets[parent.number] or parent.status):
                    targets[parent.number] = settings.option(_model.IN_PROGRESS)
        result = []
        for t in tasks:
            target = targets[t.number]
            if (t.on_board or t.open) and target is not None and target != t.status:
                try:
                    self.store.ensure()
                    self.store.write(self.store.item(t.number), self.store.info().field(settings.status_field), target)
                    t = replace(t, status=target, stage=self.store.stage_of(target), on_board=True)
                except TaskError as error:
                    self.notices.append(f"#{t.number} の段階を GitHub で合わせられませんでした（{error.message}）。")
            result.append(t)
        return result

    # 内部 -----------------------------------------------------------------------------

    def _op(self, name: str) -> str:
        return operation(self.command, name)

    def _shared(self) -> None:
        """置き場所を作った・引き継いだときに共有した人を、1回だけ知らせる。"""
        if self.store.shared:
            self.notices.append(f"共同作業者（{', '.join(self.store.shared)}）も、タスクの計画・段階を書けるようにしました。")
            self.store.shared = ()

    def _open_subtasks(self, number: int) -> list[_github.IssueInfo]:
        return sorted((s for s in self.github.sub_issues(self.root, number) if s.state == "open"),
                      key=lambda s: s.number)

    def _parent_follows(self, status: str | None) -> bool:
        """子が始まったら作業中にする親の状態：未設定・未着手・計画の段階（段階に当てていない選択肢）。"""
        return status is None or status == self.board.option(_model.TODO) or status not in self.board.stage_options

    def _expected_stage(self, state: str, current: str | None, work: WorkState) -> str | None:
        """Issue・PR・作業空間から決まる作業の段階。決まらなければ（計画の段階・作業空間なしの作業中）None。"""
        settings = self.board
        if state != "open":
            return _model.DONE
        if work.pull_request:
            return _model.IN_PROGRESS if work.draft else _model.IN_REVIEW
        if work.branch:
            return _model.IN_PROGRESS
        if current is None or current in (settings.option(_model.DONE), settings.stages.get(_model.IN_REVIEW)):
            return _model.TODO
        return None

    def __repr__(self) -> str:
        return f"Tracker({str(self.root)!r})"


def _missing_last(value, number: int) -> tuple:
    return (value is None, value if value is not None else 0, number)
