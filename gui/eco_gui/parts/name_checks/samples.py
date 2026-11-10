SAMPLES = [
    {"name": "いくつか選んでいる", "props": {"title": "渡すツール", "hint_key": "summary", "items": ["status", "task_*"], "rows": [
        {"name": "status", "summary": "今の状態を表示します。"}, {"name": "diff", "summary": "差分を表示します。"},
        {"name": "task_commit", "summary": "コミットします。"}, {"name": "task_push", "summary": "push します。"}]}},
    {"name": "すべて", "props": {"title": "使えるスキル", "items": ["*"], "rows": [{"name": "release-notes"}, {"name": "pdf"}]}},
    {"name": "パターンなし", "props": {"title": "起動してよい子", "label_key": "title", "patterns": False, "items": ["worker"],
                                 "rows": [{"name": "lead", "title": "進行役"}, {"name": "worker", "title": "作業役"}]}},
    {"name": "読み込み中", "props": {"title": "渡すツール", "loading": True}},
    {"name": "誤り", "props": {"title": "渡すツール", "error": "一覧を読めません"}},
]
