SAMPLES = [
    {"name": "2つのブランチへの提出", "props": {
        "tasks": [
            {"number": 12, "title": "ログイン画面", "assignees": ["superFUKA"],
             "submission": {"number": 13, "state": "open", "base": "main", "draft": True, "partial": False}},
            {"number": 20, "title": "検索を足す", "assignees": ["octocat"],
             "submission": {"number": 21, "state": "open", "base": "develop", "draft": False, "partial": True}},
            {"number": 22, "title": "並べ替え", "assignees": [],
             "submission": {"number": 23, "state": "open", "base": "develop", "draft": False, "partial": False}},
        ],
        "branches": [{"name": "develop", "submitted_to": "main", "submission": {"number": 30, "state": "open", "draft": False, "partial": False}},
                     {"name": "main", "submitted_to": None, "submission": None}],
        "to_review": [{"number": 20}],
        "access": {"login": "superFUKA", "take_in": {"main": {"allowed": False, "owners": "管理者"},
                                                      "develop": {"allowed": True, "owners": "develop を作った superFUKA と管理者"}},
                   "take_in_other": {"allowed": False, "owners": "管理者"}}}},
    {"name": "ない", "props": {"tasks": []}},
    {"name": "読み込み中", "props": {"tasks": [], "loading": True}},
    {"name": "誤り", "props": {"tasks": [], "error": "モジュールではありません"}},
]
