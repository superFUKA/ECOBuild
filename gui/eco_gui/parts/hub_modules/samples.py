SAMPLES = [
    {"name": "ふつう", "props": {
        "rows": [
            {"path": "C:/work/ECOSTL", "exists": True, "repository": "acme/ECOSTL", "url": "https://github.com/acme/ECOSTL.git", "type": "cpp"},
            {"path": "C:/work/ECOCppLogger", "exists": True, "repository": "acme/ECOCppLogger", "url": "https://github.com/acme/ECOCppLogger.git", "type": "cpp"},
            {"path": "C:/work/ECOBuild", "exists": True, "repository": "acme/ECOBuild", "url": "https://github.com/acme/ECOBuild.git", "type": "python"},
            {"path": "C:/work/Gone", "exists": False, "repository": "acme/Gone", "url": "https://github.com/acme/Gone.git", "type": "python"},
            {"path": "C:/work/Broken", "exists": True, "repository": None, "url": None, "type": ""},
            {"path": "C:/work/Old", "exists": True, "repository": "acme/Old", "url": "https://github.com/acme/Old.git", "type": "cpp"},
        ],
        "legacy": [
            {"path": "C:/work/ECOBuild-2", "exists": True, "repository": "acme/ECOBuild", "url": "https://github.com/acme/ECOBuild.git", "branch": "task/12-login", "task": 12},
            {"path": "C:/work/Lost", "exists": False, "repository": "acme/Lost", "url": "", "branch": "main", "task": None},
        ],
        "known": [
            {"repository": "acme/ECOSTL", "type": "cpp", "archived": False, "description": ""},
            {"repository": "acme/Old", "type": "cpp", "archived": True, "description": "前の試作"},
            {"repository": "acme/Older", "type": "python", "archived": True, "description": ""},
        ]}},
    {"name": "空", "props": {"rows": [], "known": []}},
    {"name": "アーカイブ済みだけ", "props": {"rows": [], "known": [{"repository": "acme/Old", "type": "cpp", "archived": True, "description": "前の試作"}]}},
    {"name": "読み込み中", "props": {}},
]
