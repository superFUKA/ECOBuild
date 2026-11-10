"""モジュール › メンバー：共同作業者と招待中の人。招待する・外す。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "メンバー", "width": 1280, "height": 820},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["title", "me", "members", "invite"]},
        {"id": "nav", "screen": "menu", "args": {"current": "members", "module": {"arg": "module"}}},
        {"id": "title", "part": "note", "props": {"text": "メンバー", "heading": True}},
        {"id": "me", "part": "note", "props": {"prefix": "あなた："}},
        {"id": "members", "part": "table", "props": {
            "columns": [{"key": "login", "label": "アカウント"}, {"key": "role", "label": "役割"}, {"key": "invited", "label": "状態"}],
            "key": "login",
            "actions": [{"name": "remove", "label": "外す"}],
            "labels": {
                "role": {"read": "読む", "args": {"module": {"arg": "module"}}, "triage": "タスクの整理", "write": "書き込み", "maintain": "管理の一部", "admin": "管理者"},
                "invited": {"true": "招待中", "false": ""},
            },
            "empty_text": "共同作業者はまだいません。",
        }},
        {"id": "invite", "layout": "row", "children": ["user", "role", "add"]},
        {"id": "user", "part": "text-input", "props": {"title": "GitHub のユーザー名", "placeholder": "例：octocat"}},
        {"id": "role", "part": "select", "props": {"title": "役割（組織のリポジトリだけ）", "options": [
            {"value": "", "label": "（既定）"}, {"value": "read", "label": "読む"}, {"value": "triage", "label": "タスクの整理"},
            {"value": "write", "label": "書き込み"}, {"value": "maintain", "label": "管理の一部"}, {"value": "admin", "label": "管理者"},
        ]}},
        {"id": "add", "part": "button", "props": {"label": "＋ 招待", "primary": True}},
    ],
    "bindings": [
        # 読む
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "me.text", "from": "login"},
        {"read": "module members", "args": {"module": {"arg": "module"}}, "to": "members.rows"},
        # 入力 → 共有の値
        {"on": "user.changed", "set": {"user": {"payload": "text"}}},
        {"on": "role.changed", "set": {"role": {"payload": "value"}}},
        # 入力 → ecobuild のコマンド（人が打つのと同じ：ecobuild module members add <user> [--role <role>]）
        {"on": "add.pressed", "run": "module members add", "args": {"module": {"arg": "module"}, "user": {"value": "user"}, "role": {"value": "role"}}},
        {"on": "members.action", "run": "module members remove", "args": {"module": {"arg": "module"}, "user": {"payload": "id"}}},
    ],
}
