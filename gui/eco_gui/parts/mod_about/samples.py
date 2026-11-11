SAMPLES = [
    {"name": "C++（Project と依存先）", "props": {"data": {
        "name": "Game", "type": "cpp", "root": "C:/work/Game", "repository": "octocat/Game", "url": "https://github.com/octocat/Game",
        "private": True, "archived": False, "default_base": "main", "projects": ["Game", "GameTest"], "dependencies": ["ECOSTL", "Calc"],
        "workspaces": [{"name": "12", "path": "C:/work/Game/.ecobuild/w/12", "branch": "task/12-login", "task": 12}], "format": 5, "latest_format": 5}}},
    {"name": "アーカイブ済み・作業空間なし・以前の仕様", "props": {"data": {
        "name": "Calc", "type": "python", "root": "C:/work/Calc", "repository": "octocat/Calc", "url": "https://github.com/octocat/Calc",
        "private": False, "archived": True, "default_base": "main", "projects": [], "dependencies": [], "workspaces": [], "format": 3, "latest_format": 5}}},
    {"name": "GitHub が分からない", "props": {"data": {"name": "Local", "type": "generic", "root": "C:/work/Local", "repository": None, "url": None,
                                                 "private": None, "archived": False, "default_base": "main", "projects": [], "dependencies": []}}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "モジュールではありません"}},
]
