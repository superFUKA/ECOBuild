"""作業空間 › テストを作成（いくつも）：選んだファイルのテストを、それぞれの既定の場所に作る（窓の中に重ねて開く。前の GUI と同じ）。

1回のコマンド（ecobuild file test <ファイル…>）。作れないもの（テストが既にある等）は飛ばして知らせる。作ったら、エクスプローラーで選んで開く。"""

ARGS = {"module": ".", "paths": []}  # 作業空間のフォルダー・テストを作るファイル

SCREEN = {
    "root": "page",
    "window": {"title": "テストを作成", "width": 560, "height": 380},
    "nodes": [
        {"id": "page", "layout": "column", "look": "ws-dialog", "children": ["title", "targets", "text", "foot"]},
        {"id": "title", "part": "note", "props": {"text": "テストを作成", "heading": True}},
        {"id": "targets", "part": "string-list", "props": {"items": {"arg": "paths"}}},
        {"id": "text", "part": "note", "props": {"text": "のテストを、組のテスト用Projectの同じ構成の場所に作ります（テストが既にあるファイルは、そのままにします）。"}},
        {"id": "foot", "layout": "row", "look": "actions", "children": ["cancel", "make"]},
        {"id": "cancel", "part": "button", "props": {"label": "キャンセル"}},
        {"id": "make", "part": "button", "props": {"label": "作成", "primary": True}},
    ],
    "bindings": [
        {"on": "make.pressed", "run": "file test", "args": {"module": {"arg": "module"}, "paths": {"arg": "paths"}},
         "parent": {"made": {"result": "paths"}}, "close": True,
         "notify": "テストを作りました。[作らなかったもの：{skipped.0.path}（{skipped.0.reason}）など]"},
        {"on": "cancel.pressed", "close": True},
    ],
}
