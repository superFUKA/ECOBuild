SAMPLES = [
    {"name": "ファイルを選んでいる", "props": {"paths": ["README.md", "src/app.py", "src/util/text.py", "tests/test_app.py"],
                                     "selected": "src/util/text.py", "checked": ["README.md", "src/app.py"]}},
    {"name": "フォルダーを選んでいる", "props": {"paths": ["README.md", "src/app.py", "src/util/text.py"], "selected": "src/util"}},
    {"name": "空", "props": {"paths": []}},
    {"name": "読み込み中", "props": {"paths": [], "loading": True}},
    {"name": "誤り", "props": {"paths": [], "error": "モジュールではありません"}},
]
