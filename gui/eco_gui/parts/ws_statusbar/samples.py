SAMPLES = [
    {"name": "未Push・遅れ・衝突", "props": {"status": {"task": 12, "ahead": 2, "base": "main"},
                                      "remote": {"branch": "task/12-login", "base_behind": 3, "base_conflicts": ["src/app.py"]}, "run": "bad"}},
    {"name": "Push済み・実行中", "props": {"status": {"task": 12, "ahead": 0, "base": "main"}, "remote": {"branch": "task/12-login", "base_behind": 0}, "run": "run"}},
    {"name": "成功・出力を隠している", "props": {"status": {"task": 12, "ahead": 0}, "run": "ok", "output_hidden": True}},
    {"name": "ほかのブランチ・未確認", "props": {"status": {"branch": "main", "task": None}}},
]
