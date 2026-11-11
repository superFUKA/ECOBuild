SAMPLES = [
    {"name": "個人のリポジトリ（管理者）", "props": {
        "account": {"login": "octocat", "role": "admin", "admin": True, "owner": "octocat", "owner_type": "User"},
        "members": [{"login": "octocat", "role": "admin", "invited": False}, {"login": "hubot", "role": "write", "invited": False},
                    {"login": "newbie", "role": "write", "invited": True}]}},
    {"name": "組織のリポジトリ（役割を変えられる）", "props": {
        "account": {"login": "octocat", "role": "admin", "admin": True, "owner": "acme", "owner_type": "Organization"},
        "members": [{"login": "octocat", "role": "admin", "invited": False}, {"login": "hubot", "role": "triage", "invited": False}]}},
    {"name": "管理者でない", "props": {"account": {"login": "hubot", "role": "write", "admin": False, "owner": "octocat", "owner_type": "User"}, "members": []}},
    {"name": "空", "props": {"account": {"login": "octocat", "role": "admin", "admin": True, "owner": "octocat", "owner_type": "User"},
                           "members": [{"login": "octocat", "role": "admin", "invited": False}]}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "誤り", "props": {"account": {"login": "octocat", "role": "admin", "admin": True}, "error": "GitHub に問い合わせられません"}},
]
