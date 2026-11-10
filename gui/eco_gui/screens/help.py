"""モジュール › ヘルプ：モジュールの窓の中で、ヘルプ（画面 help-guide）を見せる。"""

ARGS = {"module": "."}  # モジュールのフォルダー（メニューで戻るため）

SCREEN = {
    "root": "page",
    "window": {"title": "ヘルプ", "width": 1280, "height": 820},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["body"]},
        {"id": "nav", "screen": "menu", "args": {"current": "help", "module": {"arg": "module"}}},
        {"id": "body", "screen": "help-guide"},
    ],
    "bindings": [],
}
