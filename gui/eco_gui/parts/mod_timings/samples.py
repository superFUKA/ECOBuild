SAMPLES = [
    {"name": "ふつう", "props": {"data": {
        "pipelines": [{"name": "full", "steps": ["build", "test"], "tests": []}, {"name": "quick", "steps": ["conflict_markers"], "tests": []}],
        "triggers": {"before-submit": ["full"], "before-commit": ["quick"]}, "local": {"before-commit": ["full"], "after-sync": ["full"]}}}},
    {"name": "パイプラインがない", "props": {"data": {"pipelines": [], "triggers": {}, "local": {}}}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "モジュールではありません"}},
]
