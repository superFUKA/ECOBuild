"""モジュール › CI › ログ：実行の、失敗した手順の出力を見せる（中に重ねる窓）。"""

ARGS = {"module": ".", "run": 0}  # モジュールのフォルダー・実行の番号

SCREEN = {
    "root": "page",
    "window": {"title": "失敗した手順のログ", "width": 980, "height": 640},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["head", "log"]},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "close"]},
        {"id": "title", "part": "note", "props": {"text": "失敗した手順のログ", "heading": True}},
        {"id": "close", "part": "button", "props": {"label": "閉じる"}},
        {"id": "log", "part": "text-view", "props": {"empty_text": "（ログはありません）"}},
    ],
    "bindings": [
        {"read": "ci logs", "args": {"module": {"arg": "module"}, "run": {"arg": "run"}}, "to": "log.text", "from": "log"},
        {"on": "close.pressed", "close": True},
    ],
}
