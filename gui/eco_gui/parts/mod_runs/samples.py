SAMPLES = [
    {"name": "ふつう", "props": {"url": "https://github.com/octocat/Calc", "branches": [{"name": "main", "remote": True}, {"name": "develop", "remote": True},
                                                                                       {"name": "local-only", "remote": False}], "rows": [
        {"id": 905, "workflow": "ecobuild", "branch": "main", "event": "push", "status": "in_progress", "conclusion": None,
         "created": "2026-11-10T10:00:00+09:00", "url": "https://github.com/octocat/Calc/actions/runs/905"},
        {"id": 904, "workflow": "ecobuild", "branch": "task/12-login", "event": "pull_request", "status": "completed", "conclusion": "success",
         "created": "2026-11-10T09:30:00+09:00", "url": "https://github.com/octocat/Calc/actions/runs/904"},
        {"id": 903, "workflow": "ecobuild", "branch": "develop", "event": "workflow_dispatch", "status": "completed", "conclusion": "failure",
         "created": "2026-11-09T18:02:00+09:00", "url": "https://github.com/octocat/Calc/actions/runs/903"},
        {"id": 902, "workflow": "ecobuild", "branch": "develop", "event": "schedule", "status": "completed", "conclusion": "timed_out",
         "created": "2026-11-09T03:00:00+09:00", "url": "https://github.com/octocat/Calc/actions/runs/902"},
        {"id": 901, "workflow": "ecobuild", "branch": "main", "event": "push", "status": "completed", "conclusion": "cancelled",
         "created": "2026-11-08T12:00:00+09:00", "url": ""},
    ]}},
    {"name": "ブランチで絞っている", "props": {"branch": "develop", "branches": [{"name": "main", "remote": True}, {"name": "develop", "remote": True}],
                                       "rows": [], "branch_rows": [
        {"id": 903, "workflow": "ecobuild", "branch": "develop", "event": "workflow_dispatch", "status": "completed", "conclusion": "failure",
         "created": "2026-11-09T18:02:00+09:00", "url": "https://github.com/octocat/Calc/actions/runs/903"}]}},
    {"name": "空", "props": {"rows": []}},
    {"name": "読み込み中", "props": {"rows": [], "loading": True}},
    {"name": "誤り", "props": {"rows": [], "error": "GitHub に問い合わせられません"}},
]
