"""ハブ › アカウント：ログイン中の GitHub のアカウントと権限、コミットの作成者、新しいモジュールの所有者。左下のアカウントから、窓の中に重ねて開く。"""

SCREEN = {
    "root": "page",
    "window": {"title": "アカウント", "width": 560, "height": 600},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["title", "account", "actions"]},
        {"id": "title", "part": "note", "props": {"text": "アカウント", "heading": True}},
        {"id": "account", "part": "hub-account", "look": "grow"},
        {"id": "actions", "layout": "row", "look": "actions", "children": ["reload", "close"]},
        {"id": "reload", "part": "button", "props": {"label": "読み直す", "hint": "ログインし直した・権限を足した後に"}},
        {"id": "close", "part": "button", "props": {"label": "閉じる", "primary": True}},
    ],
    "bindings": [
        {"read": "account show", "to": "account.account"},
        {"read": "doctor", "to": "account.doctor", "from": "items"},
        {"read": "config list", "to": "account.config"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "close.pressed", "close": True},
        # ecobuild setup --name <名前> --email <メール>・ecobuild config set owner <所有者>・config unset owner
        {"on": "account.author", "run": "setup", "args": {"name": {"payload": "name"}, "email": {"payload": "email"}},
         "notify": "コミットの作成者を保存しました。"},
        {"on": "account.owner", "run": "config set", "args": {"key": "owner", "value": {"payload": "owner"}}, "notify": "既定の所有者を保存しました。"},
        {"on": "account.owner_reset", "run": "config unset", "args": {"key": "owner"}, "notify": "ログイン中のユーザーを使います。"},
    ],
}
