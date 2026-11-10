SAMPLES = [
    {"name": "選んでいない", "props": {"title": "写すプリセット", "label_key": "title",
                                 "rows": [{"name": "lead", "title": "進行役"}, {"name": "worker", "title": "作業役"}]}},
    {"name": "選んでいる", "props": {"title": "写すプリセット", "rows": [{"name": "lead"}, {"name": "worker"}], "value": "worker"}},
    {"name": "読み込み中", "props": {"title": "写すプリセット", "loading": True}},
    {"name": "誤り", "props": {"title": "写すプリセット", "error": "一覧を読めません"}},
]
