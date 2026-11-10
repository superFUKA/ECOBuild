SAMPLES = [
    {"name": "ふつう", "props": {
        "details": [{"key": "priority", "label": "優先度"}, {"key": "due", "label": "期限"}],
        "items": [{"task": {"number": 12, "title": "ログイン画面", "priority": "High", "due": "2026-11-20"}, "reasons": ["優先度が高い", "期限が近い"]},
                  {"task": {"number": 13, "title": "ログを残す", "priority": None, "due": None}, "reasons": []}]}},
    {"name": "空", "props": {"items": [], "empty_text": "着手できるタスクはありません。"}},
    {"name": "読み込み中", "props": {"items": [], "loading": True}},
    {"name": "誤り", "props": {"items": [], "error": "モジュールではありません"}},
]
