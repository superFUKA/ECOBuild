"""モジュール › ブランチ：左に共有ブランチの木、右に選んだブランチの詳細。作る・消す。取り込み・提出の画面を開く。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "ブランチ", "width": 1280, "height": 820, "refresh": {"focus": True, "every": 180}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "body"]},
        {"id": "nav", "screen": "menu", "args": {"current": "branches", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "tools"]},
        {"id": "title", "part": "note", "props": {"text": "ブランチ", "heading": True}},
        {"id": "tools", "layout": "row", "look": "tools", "children": ["log", "reload", "create"]},
        {"id": "log", "part": "button", "props": {"label": "ログ", "quiet": True, "hint": "すべてのブランチの履歴を、ログの画面で開く"}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す", "quiet": True}},
        {"id": "create", "part": "button", "props": {"label": "＋ ブランチ", "primary": True}},
        # 左：共有ブランチの木（幅は変えられる）。右：選んだブランチ
        {"id": "body", "layout": "split", "look": "mod-branches", "props": {"direction": "row", "sizes": [240, None]}, "children": ["tree", "side"]},
        {"id": "tree", "part": "mod-branch-tree"},
        {"id": "side", "layout": "column", "look": "mod-branch-side", "children": ["detail"]},
        {"id": "detail", "part": "mod-branch-detail"},
    ],
    "bindings": [
        {"read": "branch list", "args": {"module": {"arg": "module"}}, "to": "tree.branches"},
        {"read": "branch list", "args": {"module": {"arg": "module"}}, "to": "detail.branches"},
        {"read": "task list", "args": {"module": {"arg": "module"}, "submitted": True}, "to": "tree.submissions"},  # 届いている提出の件数
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "tree.default_base", "from": "default_base"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "detail.default_base", "from": "default_base"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "detail.creators", "from": "creators"},
        {"read": "module protection", "args": {"module": {"arg": "module"}}, "to": "detail.protection"},
        # 選ぶ
        {"on": "tree.selected", "set": {"branch": {"payload": "name"}}},
        {"value": "branch", "to": "tree.selected"},
        {"value": "branch", "to": "detail.selected"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "tree.reload", "refresh": True},
        {"on": "detail.reload", "refresh": True},
        {"on": "log.pressed", "run": "log", "args": {"module": {"arg": "module"}, "all": True, "gui": True}},
        # 作る：入力の窓（作成元の初めの値は、選んでいるブランチ）
        {"on": "create.pressed", "open": "mod-branch-new", "args": {"module": {"arg": "module"}, "base": {"value": "branch"}}, "inside": True},
        # 選んだブランチの操作
        {"on": "detail.action", "when": {"action": "merge"}, "open": "merge",
         "args": {"module": {"arg": "module"}, "name": {"payload": "name"}}, "here": True},
        {"on": "detail.action", "when": {"action": "delete"}, "run": "branch delete",
         "args": {"module": {"arg": "module"}, "name": {"payload": "name"}}, "set": {"branch": None}, "notify": "ブランチを削除しました。"},
        {"on": "detail.action", "when": {"action": "protect"}, "open": "settings", "args": {"module": {"arg": "module"}}, "here": True},
        {"on": "detail.action", "when": {"action": "unprotect"}, "run": "module protect", "args": {"module": {"arg": "module"}, "off": True},
         "notify": "保護を外しました。"},
        {"on": "detail.action", "when": {"action": "task"}, "open": "task", "args": {"module": {"arg": "module"}, "issue": {"payload": "task"}}},
    ],
}
