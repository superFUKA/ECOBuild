"""タスクの表示の共通部分（task next・overdue・sprint 等）。"""

STAGE_NAMES = {"todo": "未着手", "in_progress": "作業中", "in_review": "レビュー待ち", "done": "完了",
               "planned": "計画中"}


def plan_text(task) -> str:
    """計画の値（優先度・期限・見積もり・スプリント）を短く。task は ecotask の Task か TaskSummary。"""
    sprint = getattr(task, "sprint", None)
    sprint = getattr(sprint, "name", sprint)
    parts = [f"優先度 {task.priority}" if task.priority else None,
             f"期限 {task.due.isoformat()}" if task.due else None,
             f"見積もり {task.estimate:g}" if task.estimate is not None else None,
             sprint]
    return "・".join(p for p in parts if p)


def task_line(task) -> str:
    stage = STAGE_NAMES.get(task.stage or "", task.status or "")
    plan = plan_text(task)
    return f"#{task.number} {task.title}" + (f"〈{stage}〉" if stage else "") + (f"  {plan}" if plan else "")
