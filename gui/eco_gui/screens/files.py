"""モジュール › ファイル：ファイルの木と、選んだファイルのまだコミットしていない変更。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "ファイル", "width": 900, "height": 620},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["nav", "head", "body", "selected", "ops", "add"]},
        {"id": "nav", "screen": "menu", "args": {"current": "files", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "ファイル", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "body", "layout": "row", "children": ["tree", "diff"]},
        {"id": "tree", "part": "tree"},
        {"id": "diff", "part": "text-view", "props": {"empty_text": "ファイルを選ぶと、まだコミットしていない変更が出ます。"}},
        {"id": "selected", "part": "note", "props": {"prefix": "選んでいるファイル："}},
        {"id": "ops", "layout": "row", "children": ["destination", "move", "remove"]},
        {"id": "destination", "part": "text-input", "props": {"title": "動かす先（名前を変えるときも）", "placeholder": "例：src/new_name.py"}},
        {"id": "move", "part": "button", "props": {"label": "動かす"}},
        {"id": "remove", "part": "button", "props": {"label": "消す"}},
        {"id": "add", "layout": "row", "children": ["new_path", "do_add"]},
        {"id": "new_path", "part": "text-input", "props": {"title": "新しいファイル", "placeholder": "例：src/util.py"}},
        {"id": "do_add", "part": "button", "props": {"label": "＋ 足す", "primary": True}},
    ],
    "bindings": [
        {"read": "files", "args": {"module": {"arg": "module"}}, "to": "tree.paths", "from": "files"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "tree.selected", "set": {"file": {"payload": "path"}}},
        {"value": "file", "to": "tree.selected"},
        {"value": "file", "to": "selected.text"},
        # 足す・動かす・消す（ecobuild file add <パス>・file move <元> <先>・file remove <パス>。型が管理ファイルも合わせる）
        {"on": "new_path.changed", "set": {"new_path": {"payload": "text"}}},
        {"on": "do_add.pressed", "run": "file add", "args": {"module": {"arg": "module"}, "paths": [{"value": "new_path"}]}},
        {"on": "destination.changed", "set": {"destination": {"payload": "text"}}},
        {"on": "move.pressed", "run": "file move",
         "args": {"module": {"arg": "module"}, "source": {"value": "file"}, "destination": {"value": "destination"}}, "set": {"file": None}},
        {"on": "remove.pressed", "run": "file remove", "args": {"module": {"arg": "module"}, "paths": [{"value": "file"}]}, "set": {"file": None}},
        {"read": "diff", "args": {"module": {"arg": "module"}, "paths": [{"value": "file"}]}, "to": "diff.text"},
    ],
}
