SAMPLES = [
    {"name": "足りないものがある", "props": {"items": [
        {"id": "git", "name": "git", "ok": True, "required": True, "detail": "git version 2.55.0", "hint": ""},
        {"id": "gh_auth", "name": "gh の認証", "ok": False, "required": True, "detail": "ログインしていません",
         "hint": "gh auth login を実行してください（ブラウザでログインします）。"},
        {"id": "docker", "name": "docker（作業空間の隔離）", "ok": False, "required": False, "detail": "見つかりません",
         "hint": "ecobuild setup --docker で導入できます（作業空間をコンテナで隔離するときに使います）。"}]}},
    {"name": "そろっている", "props": {"items": [
        {"id": "git", "name": "git", "ok": True, "required": True, "detail": "git version 2.55.0", "hint": ""},
        {"id": "gh", "name": "gh", "ok": True, "required": True, "detail": "gh version 2.65.0", "hint": ""}]}},
    {"name": "読み込み中", "props": {}},
]
