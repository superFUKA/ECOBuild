"""作業空間 › いくつものファイル・フォルダーを移動：移動先のフォルダーを選んで、まとめて移す（窓の中に重ねて開く。前の GUI と同じ）。

1回のコマンド（ecobuild file move <移動元…> --into <フォルダー> [--no-test]）。テストを作る型（C++・Python）では
「対応するテストも移動する」を選べる。移したら、エクスプローラーで移動先のフォルダーを選ぶ。"""

ARGS = {"module": ".", "paths": []}  # 作業空間のフォルダー・動かすもの

SCREEN = {
    "root": "page",
    "window": {"title": "移動", "width": 560, "height": 420},
    "nodes": [
        {"id": "page", "layout": "column", "look": "ws-dialog", "children": ["form", "test"]},
        {"id": "form", "part": "ws-folder-pick", "props": {"paths": {"arg": "paths"}}},
        {"id": "test", "part": "toggle", "props": {"label": "ライブラリのヘッダー・ソース、src/ のソースなら、対応するテストも移動する", "on": True}},
    ],
    "bindings": [
        {"read": "files", "args": {"module": {"arg": "module"}}, "to": "form.files", "from": "files"},
        {"read": "files", "args": {"module": {"arg": "module"}}, "to": "form.folders", "from": "folders"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "form.projects", "from": "project_list"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "into": "module_type", "from": "type"},
        {"show": "test", "when": {"module_type": ["cpp", "python"]}},
        {"on": "test.changed", "set": {"with_test": {"payload": "on"}}},
        {"on": "form.move", "run": "file move",
         "args": {"module": {"arg": "module"}, "paths": {"arg": "paths"}, "into": {"payload": "into"}, "test": {"value": "with_test"}},
         "parent": {"moved": {"payload": "into"}}, "notify": "移動しました。", "close": True},
        {"on": "form.cancel", "close": True},
    ],
}
