"""モジュール › ヘルプ：モジュールの窓の中で、ヘルプ（画面 help-guide）を見せる。"""

ARGS = {"module": "."}  # モジュールのフォルダー（メニューで戻るため）

SCREEN = {
    "root": "page",
    "window": {"title": "ヘルプ", "width": 860, "height": 800},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["nav", "body"]},
        {"id": "nav", "screen": "menu", "args": {"current": "help", "module": {"arg": "module"}}},
        {"id": "body", "screen": "help-guide"},
    ],
    "bindings": [],
}
