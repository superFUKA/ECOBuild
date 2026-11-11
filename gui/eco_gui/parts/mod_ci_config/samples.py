SAMPLES = [
    {"name": "今の設定のとおり", "props": {"data": {
        "path": ".github/workflows/ecobuild.yml", "supported": True, "exists": True, "edited": False, "current": True,
        "os": ["windows", "linux"], "configurations": ["Debug", "Release"], "shared": True, "branches": ["main", "develop"], "default_base": "main"}}},
    {"name": "まだない", "props": {"data": {
        "path": ".github/workflows/ecobuild.yml", "supported": True, "exists": False, "edited": False, "current": False,
        "os": None, "configurations": ["Debug"], "shared": False, "branches": None, "default_base": "main"}}},
    {"name": "手で編集", "props": {"data": {
        "path": ".github/workflows/ecobuild.yml", "supported": True, "exists": True, "edited": True, "current": False,
        "os": ["linux"], "configurations": ["Debug"], "shared": False, "branches": None, "default_base": "main"}}},
    {"name": "設定と違う", "props": {"data": {
        "path": ".github/workflows/ecobuild.yml", "supported": True, "exists": True, "edited": False, "current": False,
        "os": ["linux"], "configurations": ["Debug"], "shared": False, "branches": None, "default_base": "main"}}},
    {"name": "型が非対応", "props": {"data": {"path": ".github/workflows/ecobuild.yml", "supported": False}}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "モジュールではありません"}},
]
