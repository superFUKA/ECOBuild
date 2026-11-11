SAMPLES = [
    {"name": "新しい版がある（帯）", "props": {"check": {
        "current": "55f8b2f2bc667045641dc790d30d290d77641156", "latest": "99072a3f77e01ad00ea14b269ed42f32456108f4", "ref": "main",
        "up_to_date": False, "gui": True}}},
    {"name": "最新（帯は出さない）", "props": {"check": {"current": "99072a3", "latest": "99072a3", "ref": "main", "up_to_date": True, "gui": True}}},
    {"name": "新しい版がある（1行）", "props": {"look": "status", "check": {
        "current": "55f8b2f2bc66", "latest": "99072a3f77e0", "ref": "main", "up_to_date": False, "gui": False}}},
    {"name": "最新（1行）", "props": {"look": "status", "check": {"current": "99072a3", "latest": "99072a3", "ref": "main", "up_to_date": True, "gui": True}}},
    {"name": "読み込み中", "props": {"look": "status", "loading": True}},
    {"name": "誤り", "props": {"look": "status", "error": "手元のソースから入れた ecobuild は、更新できません"}},
]
