SAMPLES = [
    {"name": "自分", "props": {
        "who": "octocat", "me": "octocat",
        "tasks": [{"number": 12, "title": "ログイン画面", "state": "open", "stage": "in_progress", "assignees": ["octocat"], "due": "2026-01-20"},
                  {"number": 13, "title": "ログを残す", "state": "open", "stage": "todo", "assignees": ["octocat"]}],
        "workload": [{"assignee": "octocat", "open": 2, "in_progress": 1, "estimate_remaining": 5, "overdue": 1}],
        "submitted": [{"number": 12, "title": "ログイン画面", "assignees": ["octocat"], "submission": {"draft": True}}],
        "reviews": [{"number": 14, "title": "提出を見てもらう", "assignees": ["hubot"], "submission": {"partial": True}}]}},
    {"name": "AI のアカウント（数はタスクから）", "props": {"who": "review-bot", "me": "octocat", "tasks": [{"number": 20, "title": "見る", "state": "open", "assignees": ["review-bot"]}]}},
    {"name": "読み込み中", "props": {"who": "octocat", "loading": True}},
    {"name": "誤り", "props": {"who": "octocat", "error": "モジュールではありません"}},
]
