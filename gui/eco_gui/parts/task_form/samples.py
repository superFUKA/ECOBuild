SAMPLES = [
    {"name": "新しいタスク（子タスク）", "props": {
        "kind": "new", "text": "12", "account": {"login": "octocat"},
        "tasks": [{"number": 12, "title": "ログイン画面", "state": "open", "assignees": ["octocat", "hubot"]}],
        "sprints": [{"name": "Sprint 2", "start": "2026-11-02", "end": "2099-11-16"}], "milestones": [{"title": "v1", "due": "2026-12-01"}]}},
    {"name": "作業を開始", "props": {
        "kind": "start", "issue": 13, "account": {"login": "octocat", "default_base": "main"},
        "accounts": [{"login": "octocat", "active": True}, {"login": "octo-agent", "active": False}],
        "branches": [{"name": "main", "local": True}, {"name": "dev", "local": False}, {"name": "task/12-login", "is_task_branch": True, "local": True}],
        "tasks": [{"number": 12, "title": "ログイン画面", "state": "open", "assignees": []}],
        "status": {"number": 13, "title": "ログを残す", "state": "open", "remote": False, "assignees": ["hubot"],
                   "blocked_by": [{"number": 11, "title": "設計", "state": "open"}]}}},
    {"name": "編集", "props": {
        "kind": "edit", "issue": 13,
        "tasks": [{"number": 12, "title": "ログイン画面", "state": "open", "assignees": []}],
        "status": {"number": 13, "title": "ログを残す", "body": "本文です。", "parent": {"number": 12}, "blocked_by": [{"number": 11}]}}},
    {"name": "担当者を追加", "props": {"kind": "assign", "issue": 12, "account": {"login": "octocat"},
                                 "tasks": [{"number": 12, "title": "ログイン画面", "assignees": ["hubot"]}, {"number": 13, "title": "ログ", "assignees": ["mona"]}]}},
    {"name": "読み込み中（タスクの状態を待つ）", "props": {"kind": "start", "issue": 13, "loading": True}},
    {"name": "候補を読み込み中（窓は待たせない）", "props": {"kind": "assign", "issue": 12, "account": {"login": "octocat"}, "loading": True,
                                           "tasks": [{"number": 12, "title": "ログイン画面", "assignees": []}]}},
    {"name": "GitHub のメンバーが届いた", "props": {"kind": "assign", "issue": 12, "account": {"login": "octocat"},
                                          "tasks": [{"number": 12, "title": "ログイン画面", "assignees": ["hubot"]}],
                                          "members": [{"login": "octocat", "role": "admin"}, {"login": "mona", "role": "write"}, {"login": "hubot", "role": "write"}]}},
    {"name": "誤り", "props": {"kind": "assign", "issue": 12, "error": "タスクを読めません"}},
]
