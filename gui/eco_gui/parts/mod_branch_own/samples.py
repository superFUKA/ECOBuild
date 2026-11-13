SAMPLES = [
    {"name": "提出できる", "props": {"name": "develop", "access": {"login": "superFUKA", "admin": False, "default_base": "main", "creators": {"develop": "superFUKA"},
                  "take_in": {"main": {"allowed": False, "owners": "管理者"}}, "take_in_other": {"allowed": False, "owners": "管理者"}},
                                   "branches": [{"name": "develop", "submission": None, "submitted_to": None}]}},
    {"name": "提出できない", "props": {"name": "feature", "access": {"login": "superFUKA", "admin": False, "default_base": "main", "creators": {"develop": "superFUKA"},
                  "take_in": {"main": {"allowed": False, "owners": "管理者"}}, "take_in_other": {"allowed": False, "owners": "管理者"}},
                                     "branches": [{"name": "feature", "submission": None, "submitted_to": None}]}},
    {"name": "提出が出ている", "props": {"name": "develop", "access": {"login": "superFUKA", "admin": False, "default_base": "main", "creators": {"develop": "superFUKA"},
                  "take_in": {"main": {"allowed": False, "owners": "管理者"}}, "take_in_other": {"allowed": False, "owners": "管理者"}}, "branches": [
        {"name": "develop", "submitted_to": "main", "submission": {"number": 30, "state": "open", "draft": False}}]}},
    {"name": "既定のブランチ", "props": {"name": "main", "access": {"login": "superFUKA", "admin": False, "default_base": "main", "creators": {"develop": "superFUKA"},
                  "take_in": {"main": {"allowed": False, "owners": "管理者"}}, "take_in_other": {"allowed": False, "owners": "管理者"}}, "branches": [{"name": "main"}]}},
    {"name": "読み込み中", "props": {"name": "develop", "loading": True}},
    {"name": "誤り", "props": {"name": "develop", "error": "読めませんでした"}},
]
