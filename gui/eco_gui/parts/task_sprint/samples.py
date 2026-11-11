SAMPLES = [
    {"name": "今のスプリント", "props": {
        "sprints": [{"name": "Sprint 1", "start": "2026-10-19", "end": "2026-11-02"}, {"name": "Sprint 2", "start": "2026-11-02", "end": "2099-11-16"}],
        "tasks": [{"number": 12, "title": "ログイン画面"}, {"number": 13, "title": "ログを残す"}],
        "status": {"sprint": {"name": "Sprint 2", "start": "2026-11-02", "end": "2099-11-16"}, "current": True, "days_left": 5,
                   "stages": {"todo": 1, "in_progress": 2, "done": 1}, "total": 4, "done": 1, "estimate_total": 8, "estimate_done": 3, "estimate_remaining": 5,
                   "unestimated": [13], "carried_over": [{"number": 12}], "tasks": [{"number": 12, "title": "ログイン画面"}]}}},
    {"name": "タスクのないスプリント", "props": {
        "sprints": [{"name": "Sprint 3", "start": "2026-11-16", "end": "2026-11-30"}],
        "status": {"sprint": {"name": "Sprint 3", "start": "2026-11-16", "end": "2026-11-30"}, "current": False, "days_left": 0, "stages": {}, "total": 0, "done": 0,
                   "estimate_total": 0, "estimate_done": 0, "estimate_remaining": 0, "unestimated": [], "carried_over": [], "tasks": []}}},
    {"name": "スプリントがない", "props": {"sprints": []}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "モジュールではありません"}},
]
