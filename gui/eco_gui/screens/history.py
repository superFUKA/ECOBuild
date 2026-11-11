"""モジュール › 履歴：左にコミットの一覧（ブランチを選べる）、右に選んだコミットの中身（変更をファイルごとに畳む）。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "履歴", "width": 1280, "height": 820, "refresh": {"focus": True}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "section", "body"]},
        {"id": "section", "screen": "branch-tabs", "args": {"current": "history", "module": {"arg": "module"}}},
        {"id": "nav", "screen": "menu", "args": {"current": "branches", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "tools"]},
        {"id": "title", "part": "note", "props": {"text": "ブランチ", "heading": True}},
        {"id": "tools", "layout": "row", "look": "tools", "children": ["graph", "reload"]},
        {"id": "graph", "part": "button", "props": {"label": "ログ", "quiet": True, "hint": "すべてのブランチの履歴を、ログの画面で開く"}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す", "quiet": True}},
        {"id": "body", "layout": "split", "look": "mod-branches", "props": {"direction": "row", "sizes": [440, None]}, "children": ["log", "side"]},
        {"id": "log", "part": "mod-commits"},
        {"id": "side", "layout": "column", "look": "mod-branch-side", "children": ["detail"]},
        {"id": "detail", "part": "mod-commit-files"},
    ],
    "bindings": [
        # 人が打つのと同じ：ecobuild log --count 50 [--branch <ブランチ>]・ecobuild show <コミット>
        {"read": "log", "args": {"module": {"arg": "module"}, "count": 50, "branch": {"value": "log_branch"}}, "to": "log.rows"},
        {"read": "branch list", "args": {"module": {"arg": "module"}}, "to": "log.branches"},
        {"on": "log.branch", "set": {"log_branch": {"payload": "name"}, "commit": None}},
        {"value": "log_branch", "to": "log.branch"},
        {"on": "log.selected", "set": {"commit": {"payload": "sha"}}},
        {"value": "commit", "to": "log.selected"},
        {"read": "show", "args": {"module": {"arg": "module"}, "commit": {"value": "commit"}}, "require": ["commit"], "to": "detail.text"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "log.reload", "refresh": True},
        {"on": "detail.reload", "refresh": True},
        {"on": "graph.pressed", "run": "log", "args": {"module": {"arg": "module"}, "all": True, "gui": True}},
    ],
}
