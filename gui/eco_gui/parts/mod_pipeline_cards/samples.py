SAMPLES = [
    {"name": "ふつう", "props": {"data": {
        "pipelines": [{"name": "full", "steps": ["generated", "conflict_markers", "build", "test"], "tests": ["tests/unit", "gui/tests"]},
                      {"name": "quick", "steps": ["conflict_markers"], "tests": []}],
        "triggers": {"before-submit": ["full"], "before-commit": ["full"]}, "local": {"after-sync": ["full"]}}}},
    {"name": "空", "props": {"data": {"pipelines": [], "triggers": {}, "local": {}}}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "モジュールではありません"}},
]
