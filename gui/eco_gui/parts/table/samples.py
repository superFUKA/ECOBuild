SAMPLES = [
    {"name": "ふつう", "props": {
        "columns": [{"key": "login", "label": "アカウント"}, {"key": "role", "label": "役割"}],
        "rows": [{"login": "octocat", "role": "write"}, {"login": "hubot", "role": "admin"}],
        "key": "login", "actions": [{"name": "remove", "label": "外す"}],
        "labels": {"role": {"write": "書き込み", "admin": "管理者"}}}},
    {"name": "入れ子の値・真偽・並び", "props": {
        "columns": [{"key": "task.number", "label": "#"}, {"key": "task.title", "label": "題名"}, {"key": "reasons", "label": "理由"},
                    {"key": "submission.base", "label": "取り込み先"}, {"key": "submission.draft", "label": "下書き"},
                    {"key": "task.assignees", "label": "担当"}],
        "rows": [{"task": {"number": 12, "title": "ログイン画面", "assignees": ["octocat", "hubot"]}, "reasons": ["期限が近い", "優先度が高い"],
                  "submission": {"base": "main", "draft": True}},
                 {"task": {"number": 13, "title": "ログを残す", "assignees": []}, "reasons": [], "submission": None}],
        "key": "task.number", "numbered": True, "actions": [{"name": "open", "label": "詳細"}],
        "labels": {"submission.draft": {"true": "下書き", "false": ""}, "submission.base": {"": "（提出なし）"}}}},
    {"name": "空", "props": {"columns": [{"key": "login", "label": "アカウント"}], "rows": [], "empty_text": "共同作業者はまだいません。"}},
    {"name": "読み込み中", "props": {"columns": [{"key": "login", "label": "アカウント"}], "rows": [], "loading": True}},
    {"name": "誤り", "props": {"columns": [{"key": "login", "label": "アカウント"}], "rows": [], "error": "管理者だけが見られます"}},
]
