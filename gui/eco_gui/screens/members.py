"""モジュール › メンバー：共同作業者と招待中の人。招待する・役割を変える・外す。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"one_per": "module", "title": "メンバー", "width": 1360, "height": 880, "refresh": {"focus": True}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "section", "body"]},
        {"id": "section", "screen": "mod-tabs", "args": {"current": "members", "module": {"arg": "module"}}},
        {"id": "nav", "screen": "menu", "args": {"current": "overview", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "モジュール", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す", "quiet": True}},
        {"id": "body", "layout": "column", "look": "mod-narrow", "children": ["members"]},
        {"id": "members", "part": "mod-members"},
    ],
    "bindings": [
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "members.account"},
        {"read": "module members", "args": {"module": {"arg": "module"}}, "to": "members.members"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "members.reload", "refresh": True},
        # 招待・役割の変更は、入力の窓。外す（招待を取り消す）は、確かめてから（ecobuild module members remove <user>）
        {"on": "members.action", "when": {"action": "invite"}, "open": "mod-member-invite", "inside": True, "args": {"module": {"arg": "module"}}},
        {"on": "members.action", "when": {"action": "role"}, "open": "mod-member-role", "inside": True,
         "args": {"module": {"arg": "module"}, "user": {"payload": "login"}, "role": {"payload": "role"}}},
        {"on": "members.action", "when": {"action": "remove"}, "run": "module members remove", "confirmed": True,
         "args": {"module": {"arg": "module"}, "user": {"payload": "login"}}, "notify": "外しました。"},
    ],
}
