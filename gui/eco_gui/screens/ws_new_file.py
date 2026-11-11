"""作業空間 › 新しいファイル：場所と名前（いくつも）を決めて、ファイルを足す（窓の中に重ねて開く）。

型が、試験や管理ファイルも合わせる（ecobuild file add <パス…> [--no-test]）。"""

ARGS = {"module": ".", "folder": ""}  # 作業空間のフォルダー・足す場所（エクスプローラーで選んでいたフォルダー）

SCREEN = {
    "root": "page",
    "window": {"title": "新しいファイル", "width": 640, "height": 420},
    "nodes": [
        {"id": "page", "layout": "column", "look": "ws-dialog", "children": ["form"]},
        {"id": "form", "part": "ws-new-file", "props": {"folder": {"arg": "folder"}}},
    ],
    "bindings": [
        {"read": "files", "args": {"module": {"arg": "module"}}, "to": "form.files", "from": "files"},
        {"on": "form.add", "run": "file add", "args": {"module": {"arg": "module"}, "paths": {"payload": "paths"}, "test": {"payload": "test"}},
         "notify": "ファイルを追加しました。", "close": True},
        {"on": "form.cancel", "close": True},
    ],
}
