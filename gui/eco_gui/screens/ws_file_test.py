"""作業空間 › テストを作成：ライブラリのヘッダー・ソースのテストを作る（窓の中に重ねて開く。前の GUI と同じ）。

場所と名前の初めは、ecobuild file test <ファイル> --dry-run の場所。作ったら、エクスプローラーで選んで開発の道具で開く。"""

ARGS = {"module": ".", "path": ""}  # 作業空間のフォルダー・テストを作るファイル

SCREEN = {
    "root": "page",
    "window": {"title": "テストを作成", "width": 640, "height": 360},
    "nodes": [
        {"id": "page", "layout": "column", "look": "ws-dialog", "children": ["form"]},
        {"id": "form", "part": "ws-file-test", "props": {"path": {"arg": "path"}}},
    ],
    "bindings": [
        {"read": "file test", "preview": True, "args": {"module": {"arg": "module"}, "paths": [{"arg": "path"}]}, "to": "form.plan"},
        {"read": "files", "args": {"module": {"arg": "module"}}, "to": "form.files", "from": "files"},
        {"on": "form.make", "run": "file test", "args": {"module": {"arg": "module"}, "paths": [{"arg": "path"}], "to": {"payload": "to"}},
         "parent": {"made": {"result": "paths"}}, "notify": "テストを作りました：{paths.0}", "close": True},
        {"on": "form.cancel", "close": True},
    ],
}
