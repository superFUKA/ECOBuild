SAMPLES = [
    {"name": "足りない", "props": {"items": [
        {"name": "git", "ok": True, "required": True}, {"name": "gh の認証", "ok": False, "required": True},
        {"name": "git の名前・メール", "ok": False, "required": True}, {"name": "docker", "ok": False, "required": False}]}},
    {"name": "そろっている（何も出さない）", "props": {"items": [{"name": "git", "ok": True, "required": True}]}},
]
