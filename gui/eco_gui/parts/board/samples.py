SAMPLES = [
    {"name": "ふつう", "props": {
        "columns": [{"key": "planned", "label": "計画中"}, {"key": "todo", "label": "未着手"}, {"key": "in_progress", "label": "作業中"}],
        "moves": ["planned", "todo"],
        "details": [{"key": "assignees", "label": "担当"}, {"key": "due", "label": "期限"}],
        "cards": [{"number": 12, "title": "ログイン画面", "stage": "in_progress", "assignees": ["octocat"], "due": "2026-11-20"},
                  {"number": 13, "title": "ログを残す", "stage": "todo", "assignees": [], "due": None},
                  {"number": 14, "title": "段階のないタスク", "stage": None, "assignees": []}]}},
    {"name": "空", "props": {"columns": [{"key": "todo", "label": "未着手"}], "cards": [], "empty_text": "開いているタスクはありません。"}},
    {"name": "読み込み中", "props": {"columns": [{"key": "todo", "label": "未着手"}], "cards": [], "loading": True}},
    {"name": "誤り", "props": {"columns": [{"key": "todo", "label": "未着手"}], "cards": [], "error": "モジュールではありません"}},
]
