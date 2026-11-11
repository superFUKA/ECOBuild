SAMPLES = [
    {"name": "作業中（ほかの人の提出が出ている）", "props": {
        "account": {"login": "octocat", "admin": True, "default_base": "main", "creators": {}},
        "sprints": [{"name": "Sprint 2", "start": "2026-11-02", "end": "2099-11-16"}], "milestones": [{"title": "v1"}],
        "status": {
            "number": 12, "title": "ログイン画面を作る", "state": "open", "url": "https://example.com/issues/12", "body": "背景：ログインがない。\n\n- 画面\n- 試験",
            "task_branch": True, "remote": True, "base": "main", "branch": "task/12-login", "workspace": "C:/work/Calc/.ecobuild/w/12",
            "assignees": ["hubot"], "labels": ["bug", "ui"], "milestone": "v1",
            "pull_request": {"state": "open", "draft": False, "partial": False}, "activity": {"mergeable": "MERGEABLE"},
            "parent": {"number": 10, "title": "認証", "state": "open"}, "subtasks": [{"number": 20, "title": "入力の検査", "state": "closed"}],
            "blocked_by": [{"number": 11, "title": "設計を決める", "state": "closed"}], "blocking": [{"number": 30, "title": "公開", "state": "open"}],
            "comments": [{"author": "octocat", "body": "見ました。\nあとは試験だけ。"}],
            "task": {"number": 12, "state": "open", "stage": "in_review", "priority": "High", "estimate": 3, "sprint": "Sprint 2", "due": "2026-01-20",
                     "planned_start": "2026-11-09", "planned_end": "2026-11-13", "created": "2026-11-01", "started": "2026-11-09", "finished": None}}}},
    {"name": "まだ始めていない", "props": {
        "account": {"login": "octocat"},
        "status": {"number": 13, "title": "ログを残す", "state": "open", "body": "", "task_branch": False, "remote": False, "assignees": [], "labels": [],
                   "comments": [], "subtasks": [], "blocked_by": [], "blocking": [], "task": {"number": 13, "state": "open", "stage": "todo", "created": "2026-11-01"}}}},
    {"name": "削除済み", "props": {
        "status": {"number": 8, "title": "やめたタスク", "state": "closed", "body": "やめた。", "task_branch": False, "remote": False, "assignees": ["octocat"],
                   "labels": [], "comments": [], "subtasks": [], "blocked_by": [], "blocking": [],
                   "task": {"number": 8, "state": "closed", "closed_reason": "not_planned", "created": "2026-10-01"}}}},
    {"name": "読み込み中", "props": {"status": None, "loading": True}},
    {"name": "誤り", "props": {"status": None, "error": "タスクが見つかりません"}},
]
