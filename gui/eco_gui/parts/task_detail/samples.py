SAMPLES = [
    {"name": "作業中（ほかの人の提出が出ている）", "props": {
        "me": "octocat",
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
    {"name": "ほかの人の提出：承認・差し戻しができない（灰色と理由）", "props": {
        "me": "octocat",
        "can_approve": {"can": False, "reason": "dev への提出の承認は、dev を作った hubot と管理者だけが行えます。"},
        "can_reject": {"can": False, "reason": "dev への提出の差し戻しは、dev を作った hubot と管理者だけが行えます。"},
        "can_finish": {"can": False, "reason": "dev への提出の取り込みは、dev を作った hubot と管理者だけが行えます。"},
        "status": {"number": 14, "title": "提出を見てもらう", "state": "open", "body": "", "task_branch": False, "remote": True, "base": "dev",
                   "assignees": ["hubot"], "labels": [], "comments": [], "subtasks": [], "blocked_by": [], "blocking": [],
                   "pull_request": {"state": "open", "draft": False, "partial": False},
                   "task": {"number": 14, "state": "open", "stage": "in_review", "created": "2026-11-01"}}}},
    {"name": "自分の下書きの提出：取り込めない", "props": {
        "me": "octocat", "can_finish": {"can": False, "reason": "タスク #15 の提出は下書きです（取り込みできません。タスクブランチで ecobuild task submit を実行して下書きを解除します）。"},
        "status": {"number": 15, "title": "下書きで出した", "state": "open", "body": "", "task_branch": True, "remote": True, "base": "main",
                   "workspace": "C:/work/Calc/.ecobuild/w/15", "assignees": ["octocat"], "labels": [], "comments": [], "subtasks": [], "blocked_by": [], "blocking": [],
                   "pull_request": {"state": "open", "draft": True, "partial": False},
                   "task": {"number": 15, "state": "open", "stage": "in_review", "created": "2026-11-01"}}}},
    {"name": "まだ始めていない", "props": {
        "me": "octocat",
        "status": {"number": 13, "title": "ログを残す", "state": "open", "body": "", "task_branch": False, "remote": False, "assignees": [], "labels": [],
                   "comments": [], "subtasks": [], "blocked_by": [], "blocking": [], "task": {"number": 13, "state": "open", "stage": "todo", "created": "2026-11-01"}}}},
    {"name": "削除済み", "props": {
        "status": {"number": 8, "title": "やめたタスク", "state": "closed", "body": "やめた。", "task_branch": False, "remote": False, "assignees": ["octocat"],
                   "labels": [], "comments": [], "subtasks": [], "blocked_by": [], "blocking": [],
                   "task": {"number": 8, "state": "closed", "closed_reason": "not_planned", "created": "2026-10-01"}}}},
    {"name": "読み込み中", "props": {"status": None, "loading": True}},
    {"name": "誤り", "props": {"status": None, "error": "タスクが見つかりません"}},
]
