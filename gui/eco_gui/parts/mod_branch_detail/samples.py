SAMPLES = [
    {"name": "既定のブランチ（保護あり）", "props": {"default_base": "main", "selected": "main",
                                         "protection": {"branch": "main", "approvals": 1, "checks": ["build"]},
                                         "branches": [
        {"name": "main", "is_task_branch": False, "base": None, "local": True, "remote": True, "submission": None, "submitted_to": None,
         "unusable": None, "merged": None, "format": 5, "latest_format": 5},
        {"name": "task/12-login", "is_task_branch": True, "base": "main", "local": True, "remote": True,
         "submission": {"number": 40, "state": "open", "draft": False}, "submitted_to": None},
        {"name": "task/13-log", "is_task_branch": True, "base": "main", "local": False, "remote": True, "submission": None, "submitted_to": None},
    ]}},
    {"name": "提出中のブランチ", "props": {"default_base": "main", "selected": "develop", "creators": {"develop": "octocat"}, "branches": [
        {"name": "develop", "is_task_branch": False, "base": "main", "local": True, "remote": True,
         "submission": {"number": 31, "state": "open", "draft": True}, "submitted_to": "main", "unusable": None, "merged": False,
         "format": 3, "latest_format": 5},
    ]}},
    {"name": "モジュールではない・手元だけ", "props": {"default_base": "main", "selected": "backup/before", "branches": [
        {"name": "backup/before", "is_task_branch": False, "base": None, "local": True, "remote": False, "submission": None, "submitted_to": None,
         "unusable": "ECOBuild のモジュールではありません", "merged": True},
    ]}},
    {"name": "空", "props": {"branches": []}},
    {"name": "読み込み中", "props": {"branches": [], "loading": True}},
    {"name": "誤り", "props": {"branches": [], "error": "GitHub に問い合わせられません"}},
]
