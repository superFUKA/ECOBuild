"""タスク管理の操作と決まりごと。データはすべてGitHubに置く（保存の層：ecotask.store）。

作業空間やPRのことは知らない。作業の流れ（ecowork）は、作業の段階が変わるときに set_stage を呼び、
ボードを合わせるとき（sync_board）は各タスクの作業の事実（開いているPR・作業空間の有無）を渡す。
判断（次にやるもの・期限・スプリント等）は ecotask.planning の関数で行う。
"""

from __future__ import annotations

import datetime as _datetime
from dataclasses import dataclass
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
    """1件の詳細：タスク・本文・コメント・親・子・先に終わるべきタスク・待っているタスク・ボードの値。"""
    task: _model.Task
    body: str
    comments: tuple[_github.Comment, ...]
    parent: TaskRef | None
    subtasks: tuple[TaskRef, ...]
    blocked_by: tuple[TaskRef, ...]
    blocking: tuple[TaskRef, ...]
    board: dict[str, str] | None                         # ボードの項目の値（ボードがなければNone）


@dataclass(frozen=True)
class WorkState:
    """ボードを合わせるときの、タスクの作業の事実（作業の流れの側が調べて渡す）。"""
    branch: bool = False                                 # 作業空間（GitHubのブランチ）がある
    pull_request: bool = False                           # 開いているPRがある
    draft: bool = False                                  # そのPRが下書き


class Tracker:
    def __init__(self, root: Path | str, *, github: _github.TaskGitHub | None = None, command: str = "",
                 board: _board.BoardSettings | None = None):
        """
        root：GitHubのリポジトリを決める手元のclone（gh はその origin を使う）。
        command：ヒントに書くCLIのコマンド名。board：つないでいるボード（なければ使わない）。
        """
        self.root = Path(root)
        self.store = TaskStore(self.root, github if github is not None else _github.GhCli(), board)
        self.command = command
        # 操作は成功したが、知らせておくこと（親タスクの子がすべて閉じた・ボードを更新できなかった等）
        self.notices: list[str] = []

    @property
    def github(self) -> _github.TaskGitHub:
        return self.store.github

    @github.setter
    def github(self, value: _github.TaskGitHub) -> None:
        self.store.github = value

    @property
    def board(self) -> _board.BoardSettings | None:
        return self.store.board

    @board.setter
    def board(self, value: _board.BoardSettings | None) -> None:
        self.store.board = value

    # タスク（Issue） ------------------------------------------------------------------

    def issue(self, number: int) -> _github.IssueInfo:
        return self.github.get_issue(self.root, number)

    def task(self, number: int) -> _model.Task:
        return self.store.task(number)

    def create(self, title: str, *, body: str = "", labels: tuple[str, ...] = (), assignees: tuple[str, ...] = (),
               parent: int | None = None, blocked_by: tuple[int, ...] = (),
               milestone: str | None = None) -> _github.IssueInfo:
        """タスクを作り、ボードがあれば未着手で加える。parent：親、blocked_by：先に終わるべきタスク。"""
        if milestone is not None:
            self.milestone_number(milestone)  # 作る前に確かめる
        info = self.github.create_issue(self.root, title, body, labels=labels, assignees=assignees)
        self.set_stage(info.number, _model.TODO)
        if parent is None and not blocked_by and milestone is None:
            return info
        try:
            self.set_relations(info.number, parent=parent, add_blocked_by=blocked_by, milestone=milestone)
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
             clear_milestone: bool = False) -> _github.IssueInfo:
        """題名・本文・ラベル・担当者（@me は自分）・親・先に終わるべきタスク・マイルストーンを変える。"""
        if title is None and body is None and parent is None and milestone is None and not (
                add_labels or remove_labels or add_assignees or remove_assignees or clear_parent
                or add_blocked_by or remove_blocked_by or clear_milestone):
            raise TaskError(ErrorCode.INVALID_ARGUMENT, "変更する内容がありません。",
                            hint="題名・本文・ラベル・担当者・親・依存・マイルストーンのどれかを指定してください。")
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

    def plan(self, number: int, **values) -> _model.Task:
        """計画の値（priority・due・estimate・sprint〔名前か current〕・clear）を設定する（ecotask.store と同じ）。"""
        self.store.plan(number, **values)
        return self.task(number)

    def comment(self, number: int, body: str) -> None:
        if not body.strip():
            raise TaskError(ErrorCode.INVALID_ARGUMENT, "コメントが空です。")
        self.github.comment_issue(self.root, number, body)

    def check_closable(self, number: int) -> None:
        """閉じてよいか：開いていて、開いている子タスクがない（親は子を終えてから閉じる）。"""
        if self.issue(number).state != "open":
            raise TaskError(ErrorCode.TASK_CLOSED, f"Issue #{number} は既に閉じています。")
        opened = self._open_subtasks(number)
        if opened:
            raise TaskError(ErrorCode.OPEN_SUBTASKS, f"#{number} には開いている子タスクがあります。",
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
                self.notices.append(f"親タスク #{parent} の子タスクはすべて閉じました"
                                    f"（親も終わりなら {self._op('task close')} {parent}）。")
        except TaskError:
            pass  # 知らせるだけなので、失敗しても操作は成功のまま

    def reopen(self, number: int) -> None:
        if self.issue(number).state == "open":
            raise TaskError(ErrorCode.INVALID_ARGUMENT, f"Issue #{number} は開いています。")
        self.github.reopen_issue(self.root, number)
        self.set_stage(number, _model.TODO)

    def check_startable(self, number: int, *, ignore_blocked: bool = False) -> None:
        """新しく作業を始めてよいか：親タスク（開いている子がある）では作業しない。先に終わるべきタスクを待つ。"""
        opened = self._open_subtasks(number)
        if opened:
            raise TaskError(ErrorCode.OPEN_SUBTASKS, f"#{number} は親タスクです（開いている子タスクがあります）。",
                            hint=f"作業は子タスクで行ってください（{self._op('task start')} <子の番号>）。",
                            details=[f"#{s.number} {s.title}" for s in opened])
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
        """ボードの項目（名前・役割の名前）で並べる。優先度・スプリント・状態は選択肢の順、期限・見積もり・日付・
        数値は小さい順。値のないものは後ろ。task_of：要素から Task を取り出す関数（既定は要素そのもの）。"""
        info = self.store.info()
        role = name if name in _model.ROLES else next(
            (r for r, f in self.board.schema.items() if f and f.casefold() == name.casefold()), None)
        status = info.field(self.board.status_field)
        if role is not None:
            if self.store.role_field(role) is None:
                raise TaskError(ErrorCode.FIELD_NOT_FOUND, f"ボードに{_model.ROLE_NAMES[role]}の項目が当てられていません。")
            pick = {_model.PRIORITY: lambda t: t.priority_rank, _model.DUE: lambda t: t.due,
                    _model.ESTIMATE: lambda t: t.estimate,
                    _model.SPRINT: lambda t: None if t.sprint is None else t.sprint.start}[role]
            return sorted(tasks, key=lambda item: _missing_last(pick(task_of(item)), task_of(item).number))
        target = info.field(name)
        if target.name == status.name:
            return sorted(tasks, key=lambda item: _sort_key(status, task_of(item).status))
        return sorted(tasks, key=lambda item: _sort_key(target, task_of(item).fields.get(target.name)))

    def details(self, number: int) -> TaskDetails:
        task = self.store.task(number)

        def refs(infos):
            return tuple(TaskRef._from(i) for i in sorted(infos, key=lambda i: i.number))

        parent = None if task.parent is None else TaskRef._from(self.issue(task.parent))
        return TaskDetails(task, self.issue(number).body, tuple(self.github.issue_comments(self.root, number)), parent,
                           refs(self.github.sub_issues(self.root, number)),
                           refs(self.github.blocked_by(self.root, number)),
                           refs(self.github.blocking(self.root, number)), self.board_values(number))

    def next_tasks(self, *, assignee: str | None = None, exclude: set[int] = frozenset(),
                   today: _datetime.date | None = None) -> list[_planning.NextTask]:
        """次にやるもの（順位と理由。ecotask.planning.next_tasks）。exclude：除くタスク（作業空間があるもの等）。"""
        today = today or _datetime.date.today()
        if self.board is None:
            self.notices.append("ボードをつないでいないので、優先度・期限・スプリントは使わずに並べています"
                                f"（{self._op('board create')}・{self._op('board use')}）。")
        else:
            missing = [_model.ROLE_NAMES[r] for r in _model.ROLES if self.store.role_field(r) is None]
            if missing:
                self.notices.append(f"ボードに{'・'.join(missing)}の項目が当てられていないので、使わずに並べています"
                                    f"（項目を足して、作業空間で {self._op('board use')} をやり直してください）。")
        tasks = self.tasks(assignee=assignee) if assignee else self.store.tasks()
        return _planning.next_tasks(tasks, today, sprints=self.sprints(), exclude=exclude)

    def deadlines(self, *, days: int = 3, today: _datetime.date | None = None) -> _planning.Deadlines:
        self._require_role(_model.DUE)
        return _planning.deadlines(self.store.tasks(), today or _datetime.date.today(), days=days)

    def sprints(self) -> list[_model.Sprint]:
        return [] if self.board is None else self.store.sprints()

    def sprint(self, name: str, *, today: _datetime.date | None = None) -> _model.Sprint:
        """スプリントを名前で探す（大文字・小文字は区別しない）。current は今日を含むもの。"""
        self._require_role(_model.SPRINT)
        sprints = self.store.sprints()
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

    # ボード（GitHub Projects） ---------------------------------------------------------

    def boards(self, owner: str | None = None) -> list[_board.BoardInfo]:
        """つなげるボードの一覧（owner を省略するとリポジトリの所有者のもの）。"""
        return self.github.list_boards(self.root, owner)

    def create_board(self, title: str | None = None, *, owner: str | None = None, sprint_start: str | None = None,
                     sprint_days: int = 14, sprints: int = 3) -> _board.BoardInfo:
        """このリポジトリ専用の標準のボードを作り、リポジトリにリンクする：Status（Backlog・Todo・In Progress・
        In Review・Done）・Priority・Estimate・Due・Sprint。題名を省略すると「<リポジトリ名> タスク」。"""
        if title is None:
            title = f"{self.github.repository_name(self.root).split('/')[-1]} タスク"
        if not title.strip():
            raise TaskError(ErrorCode.INVALID_ARGUMENT, "ボードの題名が必要です。")
        start = _parse_date(sprint_start) if sprint_start else _monday(_datetime.date.today())
        if sprint_days < 1 or sprints < 1:
            raise TaskError(ErrorCode.INVALID_ARGUMENT, "スプリントの日数と回数は1以上にしてください。")
        created = self.github.create_board(self.root, owner, title)
        status = self.github.get_board(self.root, _board.parse_url(created.url)[0], created.number).field("Status")
        self.github.set_board_options(self.root, status.id, _board.STANDARD_STATUS)
        self.github.create_board_field(self.root, created.id, "Priority", "SINGLE_SELECT",
                                       options=_board.STANDARD_PRIORITY)
        self.github.create_board_field(self.root, created.id, "Estimate", "NUMBER")
        self.github.create_board_field(self.root, created.id, "Due", "DATE")
        iterations = tuple((f"Sprint {i + 1}", (start + _datetime.timedelta(days=sprint_days * i)).isoformat(),
                            sprint_days) for i in range(sprints))
        self.github.create_board_field(self.root, created.id, "Sprint", "ITERATION", iterations=iterations)
        self.github.link_board(self.root, created.id, link=True)   # 作った時点でこのリポジトリ専用にする
        return self.github.get_board(self.root, _board.parse_url(created.url)[0], created.number)

    def board_scope(self, settings: _board.BoardSettings | None = None) -> _board.BoardScope:
        """ボードがこのリポジトリ専用か（リンクしているリポジトリ・項目のリポジトリ・公開）。"""
        settings = settings or self.require_board()
        info = self.github.get_board(self.root, settings.owner, settings.number)
        repository = self.github.repository_name(self.root)
        return _board.BoardScope(repository, info.repositories, self.github.board_item_repositories(self.root, info.id),
                                 info.public, self.github.repository_private(self.root), settings.shared)

    def check_board(self, settings: _board.BoardSettings, *, exclusive: bool = False) -> _board.BoardStatus:
        """ボードを使えるか確かめる：状態の項目が単一選択で段階に当てた選択肢があり、役割に当てた項目の型が合うか。

        exclusive：このリポジトリ専用か確かめる（他のリポジトリにリンク・他のリポジトリの項目があれば止める。
        settings.shared なら止めない）。つなぐとき（board use）に使う。
        """
        info = self.github.get_board(self.root, settings.owner, settings.number)
        scope = self.board_scope(settings)
        if exclusive and not settings.shared and (scope.other_links or scope.foreign_items):
            raise TaskError(ErrorCode.BOARD_SHARED, "このボードは、他のリポジトリと共有されています。",
                            hint="このリポジトリ専用のボードを board create で作るか、共有してよければ --shared を"
                                 "付けてください。",
                            details=[p for p in scope.problems if "リンクしていません" not in p])
        status = info.field(settings.status_field)
        if status.type != "SINGLE_SELECT":
            raise TaskError(ErrorCode.INVALID_ARGUMENT, f"フィールド {status.name} は単一選択ではありません。",
                            hint="--status-field で、状態を表す単一選択のフィールドを指定してください。")
        missing = [stage for stage in (_model.TODO, _model.IN_PROGRESS, _model.DONE) if not settings.stages.get(stage)]
        if missing:
            raise TaskError(ErrorCode.INVALID_ARGUMENT,
                            f"作業の段階（{', '.join(missing)}）に当てる {status.name} の選択肢が決まっていません。",
                            hint="--todo・--in-progress・--done（任意で --in-review）で選択肢を指定してください。",
                            details=[o.name for o in status.options])
        for stage, name in settings.stages.items():
            if stage not in _board.STAGES:
                raise TaskError(ErrorCode.INVALID_ARGUMENT, f"作業の段階 {stage} はありません。")
            if name:
                _board.find_option(status, name)
        for role, name in settings.schema.items():
            if role not in _model.ROLES:
                raise TaskError(ErrorCode.INVALID_ARGUMENT, f"役割 {role} はありません。")
            if name:
                target = info.field(name)
                if target.type != _model.ROLE_TYPES[role]:
                    raise TaskError(ErrorCode.INVALID_ARGUMENT,
                                    f"{_model.ROLE_NAMES[role]}に当てた項目 {target.name} の型が {target.type} です"
                                    f"（{_model.ROLE_TYPES[role]} が必要）。")
        return _board.BoardStatus(info.url, info.title, status.name, dict(settings.stages), info.fields,
                                  {r: n for r, n in settings.schema.items() if n}, scope)

    def link_board(self, settings: _board.BoardSettings, *, link: bool = True) -> None:
        """GitHub側でも、ボードをこのリポジトリにつなぐ（外す）。ボード自体は消さない。"""
        info = self.github.get_board(self.root, settings.owner, settings.number)
        self.github.link_board(self.root, info.id, link=link)

    def board_status(self) -> _board.BoardStatus:
        status = self.check_board(self.require_board())
        self.notices += [f"ボードの範囲：{p}" for p in status.scope.problems]
        return status

    def board_info(self) -> _board.BoardInfo:
        return self.store.info()

    def board_values(self, number: int) -> dict[str, str] | None:
        """ボード上の値（項目の名前 → 値）。ボードがなければNone、ボードにないタスクは空。"""
        if self.board is None:
            return None
        item = self.github.board_item(self.root, number, self.store.info().id)
        return {} if item is None else dict(item.values)

    def set_field(self, number: int, name: str, value: str) -> _board.TaskBoard:
        """ボードの項目を設定する（型に従って確かめる）。作業の段階に当てた状態は操作で変わるため設定しない。"""
        settings, info = self.require_board(), self.store.info()
        target = info.field(name)
        if target.type == "ITERATION" and value == "current":
            value = self.sprint("current").name  # 今日を含むスプリント
        if target.name == info.field(settings.status_field).name:
            option = _board.find_option(target, value)
            if option.name in settings.stage_options:
                raise self._stage_field_error(target.name, option.name)
        item = self.store.item(number)
        self.store.write(item, target, value)
        return _board.TaskBoard(number, item.id, self.board_values(number) or {})

    def clear_field(self, number: int, name: str) -> _board.TaskBoard:
        settings, info = self.require_board(), self.store.info()
        target = info.field(name)
        item = self.store.item(number)
        if target.name == info.field(settings.status_field).name and item.values.get(target.name) in settings.stage_options:
            raise self._stage_field_error(target.name, item.values[target.name])
        self.store.clear(item, target)
        return _board.TaskBoard(number, item.id, self.board_values(number) or {})

    def set_stage(self, number: int, stage: str) -> None:
        """作業の段階をボードの状態に反映する。作業中・レビュー待ちなら、未着手・計画中の親も作業中にする。

        ボードがなければ何もしない。失敗しても操作は成功のまま、知らせて board sync を案内する。
        """
        if self.board is None:
            return
        option = self.board.option(stage)
        try:
            status = self.store.info().field(self.board.status_field)
            item = self.store.item(number, add=True)
            if item.values.get(status.name) != option:
                self.store.write(item, status, option)
            if stage in (_model.IN_PROGRESS, _model.IN_REVIEW):
                parent = self.github.issue_relation(self.root, number).parent
                if parent is not None:
                    parent_item = self.store.item(parent, add=True)
                    if self._parent_follows(parent_item.values.get(status.name)):
                        self.store.write(parent_item, status, self.board.option(_model.IN_PROGRESS))
        except TaskError as error:
            self.notices.append(f"ボードの #{number} を {option} にできませんでした（{error.message}）。"
                                f"{self._op('board sync')} で合わせられます。")

    def sync_board(self, work: dict[int, WorkState], *, dry_run: bool = False) -> _board.BoardSyncResult:
        """ボードを実際の状態に合わせる：開いているタスクでボードにないものを加え、状態を作業の段階
        （Issueの開閉と、work：作業空間・PR）に合わせる。子が始まった親は作業中にする。計画の段階は変えない。"""
        settings = self.require_board()
        status = self.store.info().field(settings.status_field)
        tasks = self.store.tasks(closed=True)
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
        try:
            self.notices += [f"ボードの範囲：{p}" for p in self.board_scope(settings).problems]
        except TaskError:
            pass  # 範囲の確かめは知らせるだけ
        added, changed = [], []
        for t in tasks:
            if not t.on_board and not t.open:
                continue  # 閉じたタスクは、ボードにあるものだけ合わせる
            target = targets[t.number]
            if not t.on_board:
                added.append(t.number)
            if target is not None and target != t.status:
                changed.append(_board.BoardChange(t.number, t.title, t.status, target))
            if dry_run:
                continue
            item = self.store.item(t.number, add=True) if (not t.on_board or target not in (None, t.status)) else None
            if item is not None and target is not None and target != t.status:
                self.store.write(item, status, target)
        return _board.BoardSyncResult(tuple(added), tuple(changed), dry_run)

    def require_board(self) -> _board.BoardSettings:
        if self.board is None:
            raise TaskError(ErrorCode.NO_BOARD, "ボード（GitHub Projects）をつないでいません。",
                            hint=f"{self._op('board list')} で一覧を見て、{self._op('board use')} <URL> でつなぎます"
                                 f"（なければ {self._op('board create')} <題名> で作れます）。")
        return self.board

    # 内部 -----------------------------------------------------------------------------

    def _op(self, name: str) -> str:
        return operation(self.command, name)

    def _require_role(self, role: str) -> None:
        self.require_board()
        if self.store.role_field(role) is None:
            raise TaskError(ErrorCode.FIELD_NOT_FOUND, f"ボードに{_model.ROLE_NAMES[role]}の項目が当てられていません。",
                            hint="ボードに項目を足して、作業空間で board use をやり直してください"
                                 "（board create の標準のボードには、すべてあります）。")

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

    def _stage_field_error(self, field_name: str, option: str) -> TaskError:
        settings = self.board
        command = {settings.option(_model.TODO): "task reopen／task drop",
                   settings.option(_model.IN_PROGRESS): "task start（コードを変えないタスクは --no-workspace）",
                   settings.option(_model.DONE): "task merge／task close"}.get(option, "task submit")
        return TaskError(ErrorCode.STAGE_FIELD, f"{field_name} の {option} は作業の段階なので、手では設定しません。",
                         hint=f"{self._op(command)} で変わります。計画の段階（段階に当てていない選択肢）は設定できます。")

    def __repr__(self) -> str:
        return f"Tracker({str(self.root)!r})"


def _missing_last(value, number: int) -> tuple:
    return (value is None, value if value is not None else 0, number)


def _sort_key(field_: _board.BoardField, value: str | None) -> tuple:
    if value is None:
        return (1, 0, "")
    if field_.type in ("SINGLE_SELECT", "ITERATION"):
        names = [o.name for o in field_.options]
        return (0, names.index(value) if value in names else len(names), value)
    if field_.type == "NUMBER":
        try:
            return (0, float(value), value)
        except ValueError:
            return (0, float("inf"), value)
    return (0, 0, value)  # 日付（YYYY-MM-DD）・テキストは文字の順


def _parse_date(text: str) -> _datetime.date:
    try:
        return _datetime.date.fromisoformat(text)
    except ValueError:
        raise TaskError(ErrorCode.INVALID_ARGUMENT, f"日付 {text} は YYYY-MM-DD の形で指定してください。") from None


def _monday(day: _datetime.date) -> _datetime.date:
    return day - _datetime.timedelta(days=day.weekday())
