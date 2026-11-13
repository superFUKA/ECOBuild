"""コンテナ：ある作業空間のコンテナ（作業空間の窓の「コンテナ」から開く）。モジュールの場所のコンテナは、設定のタブにも出る。"""

ARGS = {"module": "."}  # モジュール（作業空間）のフォルダー

SCREEN = {
    "root": "page",
    "window": {"one_per": "module", "title": "コンテナ", "width": 1360, "height": 880},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "page", "children": ["head", "body"]},
        {"id": "nav", "screen": "menu", "args": {"current": "settings", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "コンテナ", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "body", "screen": "container-body", "args": {"module": {"arg": "module"}}},
    ],
    "bindings": [
        {"on": "reload.pressed", "refresh": True},
    ],
}
