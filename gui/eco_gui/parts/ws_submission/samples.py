SAMPLES = [
    {"name": "提出中", "props": {"status": {"branch": "task/12-login", "task": 12, "ahead": 1, "pull_request": {
        "number": 31, "url": "https://example.invalid/acme/Calc/pull/31", "state": "open", "draft": False, "partial": False, "base": "main"}}}},
    {"name": "下書き（中間提出）", "props": {"status": {"branch": "task/12-login", "task": 12, "ahead": 0, "pull_request": {
        "number": 31, "url": "https://example.invalid/acme/Calc/pull/31", "state": "open", "draft": True, "partial": True, "base": "main"}}}},
    {"name": "取り込み済み", "props": {"status": {"branch": "task/12-login", "task": 12, "pull_request": {"number": 31, "state": "merged", "base": "main"}}}},
    {"name": "まだ提出していない", "props": {"status": {"branch": "task/12-login", "task": 12, "ahead": 2, "pull_request": None}}},
    {"name": "まだ読めていない", "props": {}},
]
