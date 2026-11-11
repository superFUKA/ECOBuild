"""ハブ › ヘルプ：使い方（手順・用語）と、コマンドの一覧。ハブの窓の中で、左のメニューと一緒に出す（中身は画面 help-guide）。"""

SCREEN = {
    "root": "page",
    "window": {"title": "ECOBuild Hub", "width": 1000, "height": 720},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "nav", "screen": "hub-menu", "args": {"current": "hub-help"}},
        {"id": "main", "layout": "column", "look": "cfg-fill-page", "children": ["guide"]},
        {"id": "guide", "screen": "help-guide"},
    ],
    "bindings": [],
}
