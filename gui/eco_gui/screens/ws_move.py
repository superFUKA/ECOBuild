"""作業空間 › 移動：ファイル・フォルダーを、別の場所へ動かす（窓の中に重ねて開く）。型が、試験や管理ファイルも合わせる。

テストを作る型（C++・Python）では「対応するテストも移動する」を選べる（外すと ecobuild file move … --no-test。前の GUI と同じ）。
動かしたら、エクスプローラーで動かした先を選ぶ。"""

ARGS = {"module": ".", "path": ""}  # 作業空間のフォルダー・動かすファイルやフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "移動", "width": 560, "height": 360},
    "nodes": [
        {"id": "page", "layout": "column", "look": "ws-dialog", "children": ["title", "source", "destination", "test", "foot"]},
        {"id": "title", "part": "note", "props": {"text": "名前の変更・移動", "heading": True}},
        {"id": "source", "part": "note", "props": {"text": {"arg": "path"}, "prefix": "動かすもの："}},
        {"id": "destination", "part": "text-input", "props": {
            "title": "移動先（モジュールからのパス。名前も書く）", "text": {"arg": "path"}, "placeholder": "例：src/util/text.py"}},
        {"id": "test", "part": "toggle", "props": {"label": "ライブラリのヘッダー・ソース、src/ のソースなら、対応するテストも移動する", "on": True}},
        {"id": "foot", "layout": "row", "look": "actions", "children": ["cancel", "move"]},
        {"id": "cancel", "part": "button", "props": {"label": "キャンセル"}},
        {"id": "move", "part": "button", "props": {"label": "移動", "primary": True}},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "into": "module_type", "from": "type"},
        {"show": "test", "when": {"module_type": ["cpp", "python"]}},
        {"on": "test.changed", "set": {"with_test": {"payload": "on"}}},
        {"on": "destination.changed", "set": {"destination": {"payload": "text"}}},
        {"on": "move.pressed", "run": "file move",
         "args": {"module": {"arg": "module"}, "paths": [{"arg": "path"}, {"value": "destination"}], "test": {"value": "with_test"}},
         "require": ["paths"], "parent": {"moved": {"value": "destination"}}, "notify": "移動しました。", "close": True},
        {"on": "cancel.pressed", "close": True},
    ],
}
