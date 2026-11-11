SAMPLES = [
    {"name": "ふつう", "props": {
        "account": {"login": "octocat", "scopes": ["gist", "project", "repo"]},
        "doctor": [{"id": "gh_auth", "ok": True, "detail": "ログイン中：octocat", "hint": ""},
                   {"id": "git_identity", "ok": True, "detail": "Octo Cat <octo@example.com>", "hint": ""}],
        "config": {"owner": "acme"}}},
    {"name": "ログインしていない・作成者が未設定", "props": {
        "account": {"login": "", "scopes": []},
        "doctor": [{"id": "gh_auth", "ok": False, "detail": "", "hint": "gh auth login を実行してください（ブラウザでログインします）。"},
                   {"id": "git_identity", "ok": False, "detail": "", "hint": "ecobuild setup --name <名前> --email <メール> で設定できます。"}]}},
    {"name": "読み込み中", "props": {}},
]
