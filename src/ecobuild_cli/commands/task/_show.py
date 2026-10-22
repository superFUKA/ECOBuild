"""タスクの表示の共通部分（task next・overdue・sprint 等）。"""

from dataclasses import replace
from pathlib import Path

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


def workers(root) -> dict[int, dict]:
    """エージェントが起動した子（子タスクの持ち主）が作業中のタスク：タスクの番号 → 名前・登録・場所・ID。
    子タスクの作業空間はこのPCのエージェントの記録から読む（root のモジュールの作業空間のものだけ）。"""
    from ecobuild import workspaces
    from ecobuild_agent import agents
    found = {}
    try:
        area = workspaces.area(workspaces.original_of(Path(root)))
    except Exception:   # モジュールの外 等
        return found
    for record in agents.all_records():
        number = (record.task or {}).get("number")
        if not record.parent or record.kind != agents.OWNER or not isinstance(number, int) or number <= 0:
            continue
        path = Path(record.workspace)
        if path.parent == area or workspaces.same(path.parent, area):
            found[number] = {"name": record.name, "registration": record.registration, "path": path, "id": record.id}
    return found


def with_worker(task, found: dict[int, dict]):
    """task（TaskSummary・TaskStatus）に作業役を足す（開いているタスクだけ）。場所が分からなければ作業役の場所にする。"""
    worker = found.get(task.number) if task.state == "open" else None
    if worker is None:
        return task
    return replace(task, worker=worker, workspace=task.workspace or worker["path"])


def worker_text(worker) -> str:
    return f"エージェント {worker['name']}（{worker.get('id')}・登録 {worker.get('registration')}）が作業中（{worker['path']}）"
