SAMPLES = [
    {"name": "既定のブランチにいない", "props": {"module": "C:/work/Calc", "modules": [
        {"path": "C:/work/Calc", "exists": True, "branch": "task/12-login", "default_branch": "main"}]}},
    {"name": "切り離された状態", "props": {"module": "C:\\work\\Calc", "modules": [
        {"path": "C:/work/Calc", "exists": True, "branch": None, "default_branch": "main"}]}},
    {"name": "既定のブランチにいる（何も出さない）", "props": {"module": "C:/work/Calc", "modules": [
        {"path": "C:/work/Calc", "exists": True, "branch": "main", "default_branch": "main"}]}},
]
