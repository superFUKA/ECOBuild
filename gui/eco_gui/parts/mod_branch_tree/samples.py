SAMPLES = [
    {"name": "ふつう", "props": {"default_base": "main", "selected": "feature/mvp", "branches": [
        {"name": "main", "is_task_branch": False, "base": None, "local": True, "remote": True, "submission": None, "submitted_to": None,
         "unusable": None, "merged": None},
        {"name": "develop", "is_task_branch": False, "base": "main", "local": True, "remote": True,
         "submission": {"number": 31, "state": "open", "draft": False}, "submitted_to": "main", "unusable": None, "merged": False},
        {"name": "feature/mvp", "is_task_branch": False, "base": "main", "local": True, "remote": True, "submission": None, "submitted_to": None,
         "unusable": None, "merged": False},
        {"name": "feature/old/look", "is_task_branch": False, "base": "main", "local": True, "remote": False, "submission": None,
         "submitted_to": None, "unusable": None, "merged": True},
        {"name": "backup/before", "is_task_branch": False, "base": None, "local": False, "remote": True, "submission": None, "submitted_to": None,
         "unusable": "ECOBuild のモジュールではありません", "merged": False},
        {"name": "task/12-login", "is_task_branch": True, "base": "feature/mvp", "local": True, "remote": True, "submission": None,
         "submitted_to": None, "unusable": None, "merged": False},
    ], "submissions": [
        {"number": 12, "title": "ログイン画面", "submission": {"number": 40, "state": "open", "draft": False, "base": "feature/mvp"}},
        {"number": 13, "title": "ログを残す", "submission": {"number": 41, "state": "open", "draft": False, "base": "feature/mvp"}},
    ]}},
    {"name": "選んでいない（既定のブランチ）", "props": {"default_base": "main", "branches": [
        {"name": "main", "is_task_branch": False, "base": None, "local": True, "remote": True, "submission": None, "submitted_to": None},
        {"name": "feature/mvp", "is_task_branch": False, "base": "main", "local": True, "remote": True, "submission": None, "submitted_to": None},
    ]}},
    {"name": "空", "props": {"branches": []}},
    {"name": "読み込み中", "props": {"branches": [], "loading": True}},
    {"name": "誤り", "props": {"branches": [], "error": "GitHub に問い合わせられません"}},
]
