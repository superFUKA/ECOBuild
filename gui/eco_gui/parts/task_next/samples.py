SAMPLES = [
    {"name": "ふつう（期限切れ・期限が近い）", "props": {
        "me": "octocat", "selected": "13", "sprints": [{"name": "Sprint 2", "start": "2026-11-02", "end": "2099-11-16"}],
        "next": [{"task": {"number": 13, "title": "ログを残す", "state": "open", "priority": "High", "due": "2026-01-20", "estimate": 2, "sprint": "Sprint 2",
                           "assignees": ["octocat"]}, "reasons": ["期限切れ（3日）", "優先度 High"]},
                 {"task": {"number": 14, "title": "検索", "state": "open", "assignees": []}, "reasons": []}],
        "overdue": {"overdue": [{"number": 13, "title": "ログを残す", "state": "open", "due": "2026-01-20", "assignees": ["octocat"]}],
                    "soon": [{"number": 15, "title": "公開の準備", "state": "open", "due": "2099-11-14", "assignees": ["review-bot"]}], "days": 7}}},
    {"name": "自分の担当（着手できるものなし）", "props": {
        "filter": {"assignee": "@me"}, "next": [{"task": {"number": 14, "title": "検索", "assignees": []}, "reasons": []}],
        "mine": [], "overdue": {"overdue": [], "soon": []}}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "モジュールではありません"}},
]
