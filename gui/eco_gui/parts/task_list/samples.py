SAMPLES = [
    {"name": "ふつう（完了・削除も表示）", "props": {
        "me": "octocat", "selected": "13", "foot": True, "filter": {"closed": True, "deleted": True},
        "sprints": [{"name": "Sprint 1", "start": "2026-10-19", "end": "2026-11-02"}, {"name": "Sprint 2", "start": "2026-11-02", "end": "2099-11-16"}],
        "tasks": [
            {"number": 12, "title": "ログイン画面", "state": "open", "stage": "in_progress", "assignees": ["octocat"], "priority": "High", "due": "2026-01-20",
             "estimate": 3, "sprint": "Sprint 2", "task_branch": True, "remote": True, "blocked_by": 0, "subtasks": 3, "subtasks_done": 1},
            {"number": 13, "title": "ログを残す", "state": "open", "stage": "todo", "assignees": [], "priority": "Middle", "due": "2099-12-01", "estimate": None,
             "sprint": "Sprint 1", "blocked_by": 2, "subtasks": 0},
            {"number": 14, "title": "提出を見てもらう", "state": "open", "stage": "in_review", "assignees": ["octocat", "review-bot"], "priority": "Low", "remote": True},
            {"number": 15, "title": "担当の決まったタスク", "state": "open", "stage": "todo", "assignees": ["hubot"]},
            {"number": 16, "title": "まだ詰めている", "state": "open", "stage": "planned", "assignees": []},
            {"number": 9, "title": "終わったタスク", "state": "closed", "closed_reason": "completed", "stage": "done", "assignees": ["octocat"]},
            {"number": 8, "title": "やめたタスク", "state": "closed", "closed_reason": "not_planned", "stage": "done", "assignees": []}]}},
    {"name": "絞り込み（自分）・担当の列なし", "props": {
        "me": "octocat", "start": {"assignee": "@me"}, "assignee": False,
        "tasks": [{"number": 12, "title": "ログイン画面", "state": "open", "stage": "in_progress", "assignees": ["octocat"]},
                  {"number": 13, "title": "ログを残す", "state": "open", "stage": "todo", "assignees": []}]}},
    {"name": "条件に合わない", "props": {"tasks": [{"number": 12, "title": "ログイン画面", "state": "open", "assignees": []}], "filter": {"search": "ない題名"}}},
    {"name": "空", "props": {"tasks": [], "foot": True}},
    {"name": "読み込み中", "props": {"tasks": [], "loading": True}},
    {"name": "誤り", "props": {"tasks": [], "error": "モジュールではありません"}},
]
