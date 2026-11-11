SAMPLES = [
    {"name": "消すもの・残すものがある", "props": {"preview": {
        "removed": ["task/9-終わった", "task/10-login"], "workspaces_removed": ["C:/work/Calc/.ecobuild/w/9"],
        "skipped": [{"branch": "task/11-途中", "reason": "取り込んでいないコミットがあります"}], "dry_run": True}}},
    {"name": "片付けるものがない", "props": {"preview": {"removed": [], "workspaces_removed": [], "skipped": [], "dry_run": True}}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "モジュールではありません"}},
]
