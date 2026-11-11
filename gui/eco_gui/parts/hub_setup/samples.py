SAMPLES = [
    {"name": "今の名前・メールを薄く出す", "props": {"items": [
        {"name": "git", "ok": True, "detail": "2.55"},
        {"name": "git の名前・メール", "ok": True, "detail": "Octo Cat <octo@example.com>"}]}},
    {"name": "名前・メールがまだない", "props": {"items": [{"name": "git の名前・メール", "ok": False, "detail": ""}]}},
    {"name": "準備した結果（足りないものとコマンド）", "props": {
        "items": [{"name": "git の名前・メール", "ok": True, "detail": "Octo Cat <octo@example.com>"}],
        "result": {"done": ["git が gh の認証を使うようにしました", "git の名前・メールを設定しました"],
                   "remaining": [{"name": "cmake"}, {"name": "docker"}],
                   "commands": ["winget install --id Kitware.CMake --exact", "winget install --id Docker.DockerDesktop --exact"]}}},
    {"name": "準備した結果（変更なし）", "props": {"items": [], "result": {"done": [], "remaining": [], "commands": []}}},
]
