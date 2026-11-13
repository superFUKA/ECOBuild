"""作業空間 › 削除：ファイル・フォルダー（中身ごと）を削除する（窓の中に重ねて開く。前の GUI と同じ）。

テストを作る型（C++・Python）では「対応するテストも削除する」を選べる（外すと ecobuild file remove … --no-test）。
この窓が確認を兼ねる（「削除」で、もう一度は確かめない）。"""

ARGS = {"module": ".", "paths": []}  # 作業空間のフォルダー・削除するもの

SCREEN = {
    "root": "page",
    "window": {"title": "削除", "width": 560, "height": 380},
    "nodes": [
        {"id": "page", "layout": "column", "look": "ws-dialog", "children": ["title", "targets", "text", "test", "foot"]},
        {"id": "title", "part": "note", "props": {"text": "削除", "heading": True}},
        {"id": "targets", "part": "string-list", "props": {"items": {"arg": "paths"}}},
        {"id": "text", "part": "note", "props": {"text": "を削除します（フォルダは中身ごと）。まだコミットしていない新しいファイルは、元に戻せません。"}},
        {"id": "test", "part": "toggle", "props": {"label": "ライブラリのヘッダー・ソース、src/ のソースなら、対応するテストも削除する", "on": True}},
        {"id": "foot", "layout": "row", "look": "actions", "children": ["cancel", "remove"]},
        {"id": "cancel", "part": "button", "props": {"label": "キャンセル"}},
        {"id": "remove", "part": "button", "props": {"label": "削除", "danger": True}},
    ],
    "bindings": [
        # テストを作る型だけ、テストのチェックを出す
        {"read": "module show", "args": {"module": {"arg": "module"}}, "into": "module_type", "from": "type"},
        {"show": "test", "when": {"module_type": ["cpp", "python"]}},
        {"on": "test.changed", "set": {"with_test": {"payload": "on"}}},
        {"on": "remove.pressed", "run": "file remove", "confirmed": True,
         "args": {"module": {"arg": "module"}, "paths": {"arg": "paths"}, "test": {"value": "with_test"}},
         "parent": {"file": None}, "close": True, "notify": "削除しました（コミットすると、削除が記録されます）。"},
        {"on": "cancel.pressed", "close": True},
    ],
}
