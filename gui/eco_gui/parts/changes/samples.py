SAMPLES = [
    {"name": "ふつう", "props": {"status": {"staged": ["a.py"], "unstaged": ["b.py", "c.py"], "untracked": ["new.txt"]}, "checked": ["b.py"]}},
    {"name": "変更なし", "props": {"status": {"staged": [], "unstaged": [], "untracked": []}}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "モジュールではありません"}},
]
