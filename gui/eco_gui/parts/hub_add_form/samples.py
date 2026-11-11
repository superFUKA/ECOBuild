SAMPLES = [
    {"name": "ふつう（新規作成）", "props": {
        "types": [{"name": "cpp", "new_kinds": ["app", "library", "shared", "none"], "default_new_kind": "app"},
                  {"name": "python", "new_kinds": ["app", "library", "none"], "default_new_kind": "app"},
                  {"name": "generic", "new_kinds": [], "default_new_kind": None}],
        "candidates": [
            {"repository": "acme/Calc", "type": "cpp", "private": True, "updated": "2026-11-01T10:00:00Z", "description": "計算のライブラリ", "archived": False},
            {"repository": "acme/Game", "type": "cpp", "private": False, "updated": "2026-10-20T10:00:00Z", "description": "", "archived": False},
            {"repository": "acme/Old", "type": "python", "private": True, "updated": "", "description": "", "archived": True}],
        "modules": [{"path": "C:/work/Game", "repository": "acme/Game"}],
        "owner": "acme"}},
    {"name": "型・候補を読み込み中", "props": {}},
    {"name": "実行できなかった", "props": {"problem": "GitHub に acme/Calc は既にあります。\n別の名前にするか、「GitHubから取得」で取得してください。"}},
]
