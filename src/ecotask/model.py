"""タスクのモデル。GitHubの名前（Issue・ボードの項目名）に依存しない、型の付いたタスク。

保存の層（ecotask.store）がGitHubから読んで作り、判断（ecotask.planning）と操作（ecotask.tracker）が使う。
"""

from __future__ import annotations

import datetime as _datetime
from dataclasses import dataclass, field

# 作業の段階（ボードの状態に当てたもの）。planned は計画の段階（Backlog 等、段階に当てていない選択肢）
TODO, IN_PROGRESS, IN_REVIEW, DONE, PLANNED = "todo", "in_progress", "in_review", "done", "planned"

# ボードの項目の役割（どの項目に置くかは BoardSettings.schema で決める）
PRIORITY, DUE, ESTIMATE, SPRINT = "priority", "due", "estimate", "sprint"
PLANNED_START, PLANNED_END = "planned_start", "planned_end"      # 開始予定日・終了予定日
STARTED = "started"                                              # 開始日（作業中になった日。操作が自動で書く）
PLAN_ROLES = (PRIORITY, DUE, ESTIMATE, SPRINT, PLANNED_START, PLANNED_END)   # 人・エージェントが決める計画の値
RANK_ROLES = (PRIORITY, DUE, ESTIMATE, SPRINT)                   # 次にやるもの（task next）の判断に使う
ROLES = PLAN_ROLES + (STARTED,)
ROLE_TYPES = {PRIORITY: "SINGLE_SELECT", DUE: "DATE", ESTIMATE: "NUMBER", SPRINT: "ITERATION",
              PLANNED_START: "DATE", PLANNED_END: "DATE", STARTED: "DATE"}
ROLE_NAMES = {PRIORITY: "優先度", DUE: "期限", ESTIMATE: "見積もり", SPRINT: "スプリント",
              PLANNED_START: "開始予定日", PLANNED_END: "終了予定日", STARTED: "開始日"}
DATE_ROLES = tuple(role for role, kind in ROLE_TYPES.items() if kind == "DATE")


@dataclass(frozen=True)
class Sprint:
    """スプリント（ボードのイテレーションの1期間）。end は終わりの翌日（その日は含まない）。"""
    name: str
    start: _datetime.date
    end: _datetime.date

    def contains(self, day: _datetime.date) -> bool:
        return self.start <= day < self.end

    @property
    def days(self) -> int:
        return (self.end - self.start).days


@dataclass(frozen=True)
class Task:
    """タスク（GitHubのIssue＋ボードの計画の値）。"""
    number: int
    title: str
    url: str
    state: str                                   # open / closed
    closed_reason: str | None = None             # completed / not_planned（閉じていればどちらか）
    stage: str | None = None                     # todo / in_progress / in_review / done / planned（ボードがなければNone）
    status: str | None = None                    # ボードの状態の選択肢の名前（そのまま）
    priority: str | None = None
    priority_rank: int | None = None             # 優先度の順位（ボードの選択肢の順。0 が最も高い）
    due: _datetime.date | None = None
    estimate: float | None = None
    sprint: Sprint | None = None
    planned_start: _datetime.date | None = None
    planned_end: _datetime.date | None = None
    created: _datetime.date | None = None        # 追加した日（Issueを作った日。GitHubが記録）
    started: _datetime.date | None = None        # 開始日（初めて作業中になった日。ボードの項目）
    finished: _datetime.date | None = None       # 終了日（閉じた日。GitHubが記録。開き直すと消える）
    milestone: str | None = None
    milestone_due: _datetime.date | None = None
    labels: tuple[str, ...] = ()
    assignees: tuple[str, ...] = ()
    parent: int | None = None
    subtasks: int = 0                            # 子の数
    subtasks_done: int = 0                       # そのうち閉じたもの
    blocked_by: int = 0                          # 先に終わるべきタスクのうち、開いているものの数
    blocking: int = 0                            # このタスクを待っている、開いているタスクの数
    on_board: bool = False                       # ボードに載っているか
    fields: dict[str, str] = field(default_factory=dict)   # 役割に当てていないボードの項目（そのままの値）

    @property
    def open(self) -> bool:
        return self.state == "open"

    @property
    def is_parent(self) -> bool:
        return self.subtasks > 0

    @property
    def open_subtasks(self) -> int:
        return self.subtasks - self.subtasks_done

    def overdue(self, today: _datetime.date) -> bool:
        return self.open and self.due is not None and self.due < today

    def due_within(self, today: _datetime.date, days: int) -> bool:
        """期限が今日から days 日以内（期限切れは含まない）。"""
        return self.open and self.due is not None and today <= self.due <= today + _datetime.timedelta(days=days)


def parse_date(text: str | None) -> _datetime.date | None:
    """YYYY-MM-DD（後ろに時刻があってもよい）。なければNone。"""
    return None if not text else _datetime.date.fromisoformat(text[:10])


def local_date(timestamp: str | None) -> _datetime.date | None:
    """GitHubの日時（2026-10-10T01:02:03Z）→ 手元の時間帯での日付。なければNone。"""
    if not timestamp:
        return None
    return _datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone().date()
