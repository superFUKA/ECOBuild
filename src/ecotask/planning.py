"""タスク管理の判断。Task の一覧と今日の日付だけを使う（GitHubを知らない）。

次にやるもの・期限・スプリント・担当者ごとの量・マイルストーンの進み具合。
"""

from __future__ import annotations

import datetime as _datetime
from dataclasses import dataclass

from . import model as _model


# 着手できるか ------------------------------------------------------------------------

def startable(task: _model.Task) -> bool:
    """着手できる：開いている・先に終わるべきタスクがない・開いている子がない・段階が未着手か未設定
    （計画の段階・作業中・完了は除く）。作業空間の有無は作業の流れの側が見る。"""
    return (task.open and not task.blocked_by and not task.open_subtasks
            and task.stage in (None, _model.TODO))


# 次にやるもの ------------------------------------------------------------------------

@dataclass(frozen=True)
class NextTask:
    task: _model.Task
    reasons: tuple[str, ...]           # 順位の理由（期限切れ・今のスプリント・優先度 High・期限 10/20 等）


def next_tasks(tasks: list[_model.Task], today: _datetime.date, *, sprints: list[_model.Sprint] = (),
               exclude: set[int] = frozenset()) -> list[NextTask]:
    """次にやるもの（着手できるもの）を順位の順に。①期限切れ ②今のスプリント ③優先度 ④期限の近さ
    ⑤マイルストーンの期日の近さ ⑥番号。exclude：除くタスク（作業空間があるもの等）。"""
    current = next((s for s in sprints if s.contains(today)), None)
    candidates = [t for t in tasks if startable(t) and t.number not in exclude]

    def key(task: _model.Task):
        in_sprint = current is not None and task.sprint == current
        return (not task.overdue(today), not in_sprint,
                task.priority_rank if task.priority_rank is not None else 99,
                task.due or _datetime.date.max, task.milestone_due or _datetime.date.max, task.number)

    return [NextTask(t, _reasons(t, today, current)) for t in sorted(candidates, key=key)]


def _reasons(task: _model.Task, today: _datetime.date, current: _model.Sprint | None) -> tuple[str, ...]:
    reasons = []
    if task.overdue(today):
        reasons.append(f"期限切れ（{task.due.isoformat()}）")
    if current is not None and task.sprint == current:
        reasons.append(f"今のスプリント（{current.name}）")
    if task.priority is not None:
        reasons.append(f"優先度 {task.priority}")
    if task.due is not None and not task.overdue(today):
        reasons.append(f"期限 {task.due.isoformat()}")
    if task.milestone is not None:
        reasons.append(f"マイルストーン {task.milestone}"
                       + (f"（{task.milestone_due.isoformat()}）" if task.milestone_due else ""))
    if task.blocking:
        reasons.append(f"{task.blocking} 件が待っている")
    return tuple(reasons)


# 期限 ----------------------------------------------------------------------------------

@dataclass(frozen=True)
class Deadlines:
    overdue: tuple[_model.Task, ...]   # 期限切れ（期限の古い順）
    soon: tuple[_model.Task, ...]      # days 日以内に期限（期限の近い順）
    days: int


def deadlines(tasks: list[_model.Task], today: _datetime.date, *, days: int = 3) -> Deadlines:
    by_due = sorted((t for t in tasks if t.open and t.due is not None), key=lambda t: (t.due, t.number))
    return Deadlines(tuple(t for t in by_due if t.overdue(today)),
                     tuple(t for t in by_due if t.due_within(today, days)), days)


# スプリント ------------------------------------------------------------------------------

@dataclass(frozen=True)
class SprintSummary:
    sprint: _model.Sprint
    current: bool                      # 今日を含む
    days_left: int                     # 残り日数（今日を含む。終わっていれば0、始まっていなければ全日数）
    stages: dict[str, int]             # 段階ごとの数（todo・in_progress・in_review・done・planned・none）
    total: int
    done: int                          # 閉じたもの
    estimate_total: float
    estimate_done: float
    estimate_remaining: float
    unestimated: tuple[int, ...]       # 見積もりのない開いているタスク
    tasks: tuple[_model.Task, ...]
    carried_over: tuple[_model.Task, ...]   # 前のスプリントで終わらなかった（開いたまま）タスク


def sprint_summary(tasks: list[_model.Task], sprint: _model.Sprint, today: _datetime.date) -> SprintSummary:
    members = tuple(t for t in tasks if t.sprint == sprint and not t.is_parent)
    stages: dict[str, int] = {}
    for t in members:
        stage = _model.DONE if not t.open else (t.stage or "none")
        stages[stage] = stages.get(stage, 0) + 1
    done = [t for t in members if not t.open]
    estimate_total = sum(t.estimate or 0 for t in members)
    estimate_done = sum(t.estimate or 0 for t in done)
    if today < sprint.start:
        days_left = sprint.days
    else:
        days_left = max(0, (sprint.end - today).days)
    carried = tuple(t for t in tasks if t.open and t.sprint is not None and t.sprint.end <= sprint.start
                    and not t.is_parent)
    return SprintSummary(sprint, sprint.contains(today), days_left, stages, len(members), len(done), estimate_total,
                         estimate_done, estimate_total - estimate_done,
                         tuple(t.number for t in members if t.open and t.estimate is None), members, carried)


# 担当者ごとの量 ----------------------------------------------------------------------------

@dataclass(frozen=True)
class Workload:
    assignee: str                      # 担当なしは ""
    open: int
    in_progress: int                   # 作業中・レビュー待ち
    estimate_remaining: float
    overdue: int
    tasks: tuple[int, ...]


def workload(tasks: list[_model.Task], today: _datetime.date) -> list[Workload]:
    """開いているタスク（親は除く）を担当者ごとに。量の多い順。"""
    groups: dict[str, list[_model.Task]] = {}
    for t in tasks:
        if not t.open or t.is_parent:
            continue
        for assignee in t.assignees or ("",):
            groups.setdefault(assignee, []).append(t)
    result = [Workload(name, len(ts), sum(1 for t in ts if t.stage in (_model.IN_PROGRESS, _model.IN_REVIEW)),
                       sum(t.estimate or 0 for t in ts), sum(1 for t in ts if t.overdue(today)),
                       tuple(t.number for t in ts)) for name, ts in groups.items()]
    return sorted(result, key=lambda w: (-w.estimate_remaining, -w.open, w.assignee))


# マイルストーン ----------------------------------------------------------------------------

@dataclass(frozen=True)
class MilestoneSummary:
    title: str
    due: _datetime.date | None
    total: int
    done: int
    estimate_remaining: float
    overdue_tasks: tuple[int, ...]     # 期限切れのタスク
    late: bool                         # 期日を過ぎて、開いているタスクが残っている
    open_tasks: tuple[int, ...]


def milestone_summaries(tasks: list[_model.Task], today: _datetime.date) -> list[MilestoneSummary]:
    """マイルストーンごとの進み具合（親は数えない）。期日の順。"""
    groups: dict[str, list[_model.Task]] = {}
    for t in tasks:
        if t.milestone is not None and not t.is_parent:
            groups.setdefault(t.milestone, []).append(t)
    result = []
    for title, ts in groups.items():
        due = next((t.milestone_due for t in ts if t.milestone_due), None)
        opened = [t for t in ts if t.open]
        result.append(MilestoneSummary(title, due, len(ts), len(ts) - len(opened), sum(t.estimate or 0 for t in opened),
                                       tuple(t.number for t in opened if t.overdue(today)),
                                       due is not None and due < today and bool(opened),
                                       tuple(t.number for t in opened)))
    return sorted(result, key=lambda m: (m.due or _datetime.date.max, m.title))
