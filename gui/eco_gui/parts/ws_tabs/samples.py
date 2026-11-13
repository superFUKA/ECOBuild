SAMPLES = [
    {"name": "タスクブランチ", "props": {"status": {"branch": "task/12-login", "task": 12, "ahead": 2, "unstaged": ["a.py", "b.py"], "untracked": ["c.py"],
                                              "pull_request": {"number": 31}},
                                     "task": {"number": 12, "commits": ["bbb2222 2つ目", "aaa1111 1つ目"]}, "selected": "commit"}},
    {"name": "何もない", "props": {"status": {"branch": "task/12-login", "task": 12, "ahead": 0}, "selected": "push"}},
    {"name": "提出の確認中（Push はない）", "props": {"status": {"branch": "review/31", "reviewing": 31, "reviewing_task": 12}, "selected": "submit"}},
    {"name": "ほかのブランチ（ログだけ）", "props": {"status": {"branch": "main", "task": None}, "selected": "log"}},
]
