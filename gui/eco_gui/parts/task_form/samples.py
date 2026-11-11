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
    {"name": "完了にする", "props": {"kind": "complete", "issue": 12, "status": {"number": 12, "title": "ログイン画面", "base": "main", "pull_request": {"state": "open"}}}},
    {"name": "取り込む", "props": {"kind": "finish", "issue": 12, "status": {"number": 12, "title": "ログイン画面", "base": "main", "pull_request": {"state": "open", "partial": True}}}},
    {"name": "作業を捨てる", "props": {"kind": "drop", "issue": 12}},
    {"name": "このPCから片付ける", "props": {"kind": "prune", "issue": 12}},
    {"name": "まとめて片付ける", "props": {"kind": "clean"}},
    {"name": "担当者を追加", "props": {"kind": "assign", "issue": 12, "account": {"login": "octocat"},
                                 "tasks": [{"number": 12, "title": "ログイン画面", "assignees": ["hubot"]}, {"number": 13, "title": "ログ", "assignees": ["mona"]}]}},
    {"name": "ラベルを付ける", "props": {"kind": "label", "issue": 12}},
    {"name": "承認して取り込む", "props": {"kind": "approve", "issue": 12}},
    {"name": "差し戻す", "props": {"kind": "reject", "issue": 12}},
    {"name": "読み込み中（タスクの状態を待つ）", "props": {"kind": "start", "issue": 13}},
]
