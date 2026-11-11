SAMPLES = [
    {"name": "ふつう", "props": {"data": {
        "docker_ready": True, "docker_detail": "Docker 29.1.3", "missing": ["C:\\work\\Game\\.ecobuild\\w\\12"],
        "images": [
            {"name": "ecobuild-calc:aed8e4df36", "module": "calc", "size": "1.55GB", "created": "16 minutes ago", "current": True,
             "used_by": ["C:\\work\\Calc\\.ecobuild\\w\\7"], "environment": False},
            {"name": "ecobuild-calc-env:77aa", "module": "calc", "size": "1.2GB", "created": "2 days ago", "current": True, "used_by": [], "environment": True},
            {"name": "ecobuild-calc:0001", "module": "calc", "size": "1.4GB", "created": "3 weeks ago", "current": False, "used_by": [], "environment": False},
            {"name": "ecobuild-game:0002", "module": "game", "size": "2.1GB", "created": "2 months ago", "current": False, "used_by": [], "environment": False},
        ]}}},
    {"name": "Docker が使えない", "props": {"data": {"docker_ready": False, "docker_detail": "docker が見つかりません", "missing": [], "images": []}}},
    {"name": "イメージがない", "props": {"data": {"docker_ready": True, "docker_detail": "Docker 29.1.3", "missing": [], "images": []}}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"error": "イメージの一覧を読めませんでした。"}},
]
