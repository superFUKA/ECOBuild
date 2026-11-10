"""モジュール › ファイル：ファイルの木と、選んだファイルのまだコミットしていない変更。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "ファイル", "width": 900, "height": 620},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["nav", "head", "body"]},
        {"id": "nav", "screen": "menu", "args": {"current": "files", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "ファイル", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "body", "layout": "row", "children": ["tree", "diff"]},
        {"id": "tree", "part": "tree"},
        {"id": "diff", "part": "text-view", "props": {"empty_text": "ファイルを選ぶと、まだコミットしていない変更が出ます。"}},
    ],
    "bindings": [
        {"read": "files", "args": {"module": {"arg": "module"}}, "to": "tree.paths", "from": "files"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "tree.selected", "set": {"file": {"payload": "path"}}},
        {"value": "file", "to": "tree.selected"},
        {"read": "diff", "args": {"module": {"arg": "module"}, "paths": [{"value": "file"}]}, "to": "diff.text"},
    ],
}
