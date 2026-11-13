SAMPLES = [
    {"name": "まだ書いていない", "props": {}},
    {"name": "書いて、3件選んだ", "props": {"text": "ログインの検査を足す", "checked": ["a.py", "b.py", "c.py"]}},
    {"name": "直前のコミットを修正", "props": {"text": "検査を足す", "amend": True, "checked": []}},
    {"name": "Push 済みのコミットを修正", "props": {"text": "検査を足す", "amend": True, "checked": [],
                                                       "status": {"branch": "task/12-login", "task": 12, "ahead": 0}}},
]
