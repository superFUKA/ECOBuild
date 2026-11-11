"""作業空間 › 移動：ファイル・フォルダーを、別の場所へ動かす（窓の中に重ねて開く）。型が、試験や管理ファイルも合わせる。"""

ARGS = {"module": ".", "path": ""}  # 作業空間のフォルダー・動かすファイルやフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "移動", "width": 560, "height": 320},
    "nodes": [
        {"id": "page", "layout": "column", "look": "ws-dialog", "children": ["title", "source", "destination", "foot"]},
        {"id": "title", "part": "note", "props": {"text": "移動", "heading": True}},
        {"id": "source", "part": "note", "props": {"text": {"arg": "path"}, "prefix": "動かすもの："}},
        {"id": "destination", "part": "text-input", "props": {
            "title": "移動先（モジュールからのパス。名前も書く）", "text": {"arg": "path"}, "placeholder": "例：src/util/text.py"}},
        {"id": "foot", "layout": "row", "look": "actions", "children": ["cancel", "move"]},
        {"id": "cancel", "part": "button", "props": {"label": "キャンセル"}},
        {"id": "move", "part": "button", "props": {"label": "移動", "primary": True}},
    ],
    "bindings": [
        {"on": "destination.changed", "set": {"destination": {"payload": "text"}}},
        {"on": "move.pressed", "run": "file move",
         "args": {"module": {"arg": "module"}, "source": {"arg": "path"}, "destination": {"value": "destination"}}, "require": ["destination"],
         "notify": "移動しました。", "close": True},
        {"on": "cancel.pressed", "close": True},
    ],
}
