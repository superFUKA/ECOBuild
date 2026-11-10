SAMPLES = [
    {"name": "選んでいる", "props": {
        "columns": [{"key": "repository", "label": "リポジトリ"}, {"key": "archived", "label": "状態"}],
        "key": "repository", "selected": "acme/Old", "labels": {"archived": {"true": "アーカイブ済み", "false": ""}},
        "rows": [{"repository": "acme/Calc", "archived": False}, {"repository": "acme/Old", "archived": True}]}},
    {"name": "道筋の列・時刻・行のボタン", "props": {
        "columns": [{"key": "name", "label": "名前"}, {"key": "task.number", "label": "タスク"},
                    {"key": "started_at", "label": "起動", "format": "time"}],
        "selectable": False, "actions": [{"name": "show", "label": "見る"}],
        "rows": [{"id": "a-1", "name": "lead", "task": {"number": 12}, "started_at": 1792754845.3},
                 {"id": "a-2", "name": "worker", "task": None, "started_at": None}]}},
    {"name": "空", "props": {"columns": [{"key": "name", "label": "名前"}], "rows": [], "empty_text": "モジュールはありません。"}},
    {"name": "読み込み中", "props": {"columns": [{"key": "name", "label": "名前"}], "rows": [], "loading": True}},
    {"name": "誤り", "props": {"columns": [{"key": "name", "label": "名前"}], "rows": [], "error": "GitHub に届きません"}},
]
