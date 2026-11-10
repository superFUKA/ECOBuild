SAMPLES = [
    {"name": "ふつう", "props": {
        "columns": [{"key": "login", "label": "アカウント"}, {"key": "role", "label": "役割"}],
        "rows": [{"login": "octocat", "role": "write"}, {"login": "hubot", "role": "admin"}],
        "key": "login", "actions": [{"name": "remove", "label": "外す"}],
        "labels": {"role": {"write": "書き込み", "admin": "管理者"}}}},
    {"name": "空", "props": {"columns": [{"key": "login", "label": "アカウント"}], "rows": [], "empty_text": "共同作業者はまだいません。"}},
    {"name": "読み込み中", "props": {"columns": [{"key": "login", "label": "アカウント"}], "rows": [], "loading": True}},
    {"name": "誤り", "props": {"columns": [{"key": "login", "label": "アカウント"}], "rows": [], "error": "管理者だけが見られます"}},
]
