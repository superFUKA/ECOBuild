"""モジュール › 作業空間（出している作業空間がないとき）：左のメニュー、作業空間のタブ、案内。

タブがあれば、その1つを出した画面（frame-workspace）へ、同じ窓ですぐに切り替わる。"""

ARGS = {"module": ".", "closed": []}  # モジュールのフォルダー・閉じたタブ

SCREEN = {
    "root": "page",
    "window": {"one_per": "module", "title": "ECOBuild", "width": 1360, "height": 880, "refresh": {"focus": True}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "nav", "screen": "menu", "args": {"current": "frame-workspaces", "module": {"arg": "module"}}},
        {"id": "main", "layout": "column", "look": "frame-main", "children": ["bar"]},
        {"id": "bar", "screen": "frame-bar", "args": {"module": {"arg": "module"}, "closed": {"arg": "closed"}}},
    ],
    "bindings": [],
}
