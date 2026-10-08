"""タスク管理の判断（ecotask.planning）。GitHubを使わず、Task の一覧と日付だけで確かめる。"""

import datetime

from ecotask import model as m
from ecotask import planning

TODAY = datetime.date(2026, 10, 8)
S1 = m.Sprint("Sprint 1", datetime.date(2026, 9, 21), datetime.date(2026, 10, 5))
S2 = m.Sprint("Sprint 2", datetime.date(2026, 10, 5), datetime.date(2026, 10, 19))
S3 = m.Sprint("Sprint 3", datetime.date(2026, 10, 19), datetime.date(2026, 11, 2))


def task(number, **values):
    values.setdefault("state", "open")
    values.setdefault("stage", m.TODO)
    return m.Task(number, f"t{number}", f"u{number}", **values)


def day(n):
    return TODAY + datetime.timedelta(days=n)


def test_next_tasks_order_and_reasons():
    tasks = [
        task(1, priority="Low", priority_rank=2),
        task(2, priority="High", priority_rank=0, due=day(5)),
        task(3, priority="Low", priority_rank=2, due=day(-1)),                 # 期限切れが最優先
        task(4, priority="Middle", priority_rank=1, sprint=S2),                # 今のスプリントが次
        task(5, priority="High", priority_rank=0, due=day(2)),                 # 同じ優先度なら期限の近い順
        task(6, priority="High", priority_rank=0, blocked_by=1),               # 依存待ちは除く
        task(7, priority="High", priority_rank=0, stage=m.PLANNED),            # 計画中は除く
        task(8, priority="High", priority_rank=0, stage=m.IN_PROGRESS),        # 作業中は除く
        task(9, priority="High", priority_rank=0, subtasks=2, subtasks_done=1),  # 子が残る親は除く
        task(10, priority="High", priority_rank=0),                            # 作業空間がある（exclude）
        task(11, state="closed", stage=m.DONE),
    ]
    ranked = planning.next_tasks(tasks, TODAY, sprints=[S1, S2, S3], exclude={10})
    assert [n.task.number for n in ranked] == [3, 4, 5, 2, 1]
    assert ranked[0].reasons[0] == "期限切れ（2026-10-07）"
    assert ranked[1].reasons[0] == "今のスプリント（Sprint 2）"
    assert "期限 2026-10-10" in ranked[2].reasons


def test_deadlines():
    tasks = [task(1, due=day(-3)), task(2, due=day(-1)), task(3, due=day(0)), task(4, due=day(3)), task(5, due=day(4)),
             task(6, due=day(-5), state="closed", stage=m.DONE), task(7)]
    result = planning.deadlines(tasks, TODAY, days=3)
    assert [t.number for t in result.overdue] == [1, 2]
    assert [t.number for t in result.soon] == [3, 4]


def test_sprint_summary():
    tasks = [
        task(1, sprint=S2, estimate=3, state="closed", stage=m.DONE),
        task(2, sprint=S2, estimate=2, stage=m.IN_PROGRESS),
        task(3, sprint=S2, stage=m.TODO),                                       # 見積もりなし
        task(4, sprint=S2, subtasks=2),                                         # 親は数えない
        task(5, sprint=S1, estimate=1),                                         # 前のスプリントから持ち越し
        task(6, sprint=S3, estimate=5),
    ]
    s = planning.sprint_summary(tasks, S2, TODAY)
    assert (s.current, s.days_left, s.total, s.done) == (True, 11, 3, 1)
    assert (s.estimate_total, s.estimate_done, s.estimate_remaining) == (5, 3, 2)
    assert s.unestimated == (3,) and s.stages == {"done": 1, "in_progress": 1, "todo": 1}
    assert [t.number for t in s.carried_over] == [5]
    assert planning.sprint_summary(tasks, S3, TODAY).days_left == 14


def test_workload_and_milestones():
    tasks = [
        task(1, assignees=("alice",), estimate=3, stage=m.IN_PROGRESS, milestone="v1", milestone_due=day(-1)),
        task(2, assignees=("alice",), estimate=2, due=day(-2), milestone="v1", milestone_due=day(-1)),
        task(3, assignees=("bob",), estimate=1, milestone="v2", milestone_due=day(20)),
        task(4, estimate=8),
        task(5, state="closed", stage=m.DONE, assignees=("bob",), milestone="v1", milestone_due=day(-1)),
    ]
    load = planning.workload(tasks, TODAY)
    assert [(w.assignee, w.open, w.in_progress, w.estimate_remaining, w.overdue) for w in load] == [
        ("", 1, 0, 8, 0), ("alice", 2, 1, 5, 1), ("bob", 1, 0, 1, 0)]
    v1, v2 = planning.milestone_summaries(tasks, TODAY)
    assert (v1.title, v1.total, v1.done, v1.estimate_remaining, v1.late, v1.overdue_tasks) == ("v1", 3, 1, 5, True, (2,))
    assert (v2.title, v2.late) == ("v2", False)
