SAMPLES = [
    {"name": "ふつう（完了は最近のもの）", "props": {
        "me": "octocat", "selected": "13",
        "sprints": [{"name": "Sprint 2", "start": "2026-11-02", "end": "2099-11-16"}],
        "tasks": [
            {"number": 12, "title": "ログイン画面", "state": "open", "stage": "in_progress", "assignees": ["octocat"], "priority": "High", "due": "2026-01-20",
             "estimate": 3, "sprint": "Sprint 2", "task_branch": True, "remote": True, "blocked_by": 0, "subtasks": 3, "subtasks_done": 1},
            {"number": 13, "title": "ログを残す", "state": "open", "stage": "todo", "assignees": [], "priority": "Middle", "due": "2099-12-01", "blocked_by": 2},
            {"number": 14, "title": "提出を見てもらう", "state": "open", "stage": "in_review", "assignees": ["review-bot"], "priority": "Low", "remote": True},
            {"number": 15, "title": "担当の決まったタスク", "state": "open", "stage": "todo", "assignees": ["hubot"]},
            {"number": 16, "title": "まだ詰めている", "state": "open", "stage": "planned", "assignees": []}],
        "recent": [
            {"number": 9, "title": "終わったタスク", "state": "closed", "closed_reason": "completed", "stage": "done", "assignees": ["octocat"], "finished": "2026-11-01"},
            {"number": 10, "title": "後で終わったタスク", "state": "closed", "closed_reason": "completed", "stage": "done", "assignees": [], "finished": "2026-11-05"},
            {"number": 8, "title": "やめたタスク", "state": "closed", "closed_reason": "not_planned", "stage": "done", "assignees": []}]}},
    {"name": "削除したタスクも表示", "props": {
        "filter": {"deleted": True},
        "tasks": [{"number": 13, "title": "ログを残す", "state": "open", "stage": "todo", "assignees": []},
                  {"number": 9, "title": "終わったタスク", "state": "closed", "closed_reason": "completed", "assignees": []},
                  {"number": 8, "title": "やめたタスク", "state": "closed", "closed_reason": "not_planned", "assignees": []}]}},
    {"name": "空", "props": {"tasks": []}},
    {"name": "読み込み中", "props": {"tasks": [], "loading": True}},
    {"name": "誤り", "props": {"tasks": [], "error": "モジュールではありません"}},
]
