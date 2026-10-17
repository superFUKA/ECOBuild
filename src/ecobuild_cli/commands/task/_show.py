"""タスクの表示の共通部分（task next・overdue・sprint 等）。"""

STAGE_NAMES = {"todo": "未着手", "in_progress": "作業中", "in_review": "レビュー待ち", "done": "完了",
               "planned": "計画中"}


def plan_text(task) -> str:
    """計画の値（優先度・期限・見積もり・スプリント）を短く。task は ecotask の Task か TaskSummary。"""
    sprint = getattr(task, "sprint", None)
    sprint = getattr(sprint, "name", sprint)
    start, end = getattr(task, "planned_start", None), getattr(task, "planned_end", None)
    parts = [f"優先度 {task.priority}" if task.priority else None,
             f"期限 {task.due.isoformat()}" if task.due else None,
             f"予定 {start.isoformat() if start else ''}〜{end.isoformat() if end else ''}" if start or end else None,
             f"見積もり {task.estimate:g}" if task.estimate is not None else None,
             sprint]
    return "・".join(p for p in parts if p)


def dates_text(task) -> str:
    """記録の日付（追加した日・開始日・終了日）。task は ecotask の Task か TaskSummary。"""
    parts = [f"追加 {task.created.isoformat()}" if task.created else None,
             f"開始 {task.started.isoformat()}" if task.started else None,
             f"終了 {task.finished.isoformat()}" if task.finished else None]
    return "・".join(p for p in parts if p)


def task_line(task) -> str:
    stage = STAGE_NAMES.get(task.stage or "", "")
    plan = plan_text(task)
    return f"#{task.number} {task.title}" + (f"〈{stage}〉" if stage else "") + (f"  {plan}" if plan else "")


def submission_text(state) -> str:
    """提出（PullRequestState）の短い説明：下書きの提出・中間提出・取り込み済み 等。"""
    kind = "中間提出" if state.partial else "提出"
    if state.state == "merged":
        return f"{kind}は取り込み済み"
    if state.state == "closed":
        return f"{kind}は取り下げ済み"
    return ("下書きの" if state.draft else "") + kind + "中"


def elsewhere(path, root) -> str:
    """タスクブランチが、今いるのと別のclone（このPCの）にあれば、その場所。"""
    from ecobuild import workspaces
    return "" if path is None or workspaces.same(path, root) else f"（場所：{path}）"
