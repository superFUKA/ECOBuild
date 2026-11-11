SAMPLES = [
    {"name": "ふつう（帯・遅れ・期限・日程なし）", "props": {
        "selected": "13",
        "tasks": [
            {"number": 12, "title": "ログイン画面", "state": "open", "stage": "in_progress", "assignees": ["octocat"],
             "planned_start": "2026-11-09", "planned_end": "2026-11-13", "due": "2026-11-20"},
            {"number": 13, "title": "ログを残す（終了予定を過ぎている）", "state": "open", "stage": "todo", "assignees": [],
             "planned_start": "2026-11-02", "planned_end": "2026-11-05", "due": "2026-11-06"},
            {"number": 14, "title": "提出を見てもらう", "state": "open", "stage": "in_review", "assignees": [], "planned_start": "2026-11-12", "planned_end": "2026-11-18"},
            {"number": 16, "title": "まだ詰めている", "state": "open", "stage": "planned", "assignees": [], "planned_start": "2026-11-16", "planned_end": "2026-11-27"},
            {"number": 15, "title": "予定のないタスク", "state": "open", "stage": "todo", "assignees": [], "due": "2026-11-25"},
            {"number": 17, "title": "開始予定だけ", "state": "open", "stage": "todo", "assignees": [], "planned_start": "2026-11-17"}]}},
    {"name": "空", "props": {"tasks": []}},
    {"name": "読み込み中", "props": {"tasks": [], "loading": True}},
    {"name": "誤り", "props": {"tasks": [], "error": "モジュールではありません"}},
]
