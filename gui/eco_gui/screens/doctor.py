"""環境チェック：ECOBuild を使うのに要る道具が、この PC にそろっているか。"""

SCREEN = {
    "root": "page",
    "window": {"title": "環境チェック", "width": 900, "height": 560},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["head", "items"]},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "環境チェック", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "確かめ直す"}},
        {"id": "items", "part": "table", "props": {
            "columns": [{"key": "name", "label": "道具"}, {"key": "ok", "label": "状態"}, {"key": "detail", "label": "今の状態"},
                        {"key": "hint", "label": "足りないときは"}],
            "key": "id", "labels": {"ok": {"true": "OK", "false": "要確認"}},
        }},
    ],
    "bindings": [
        {"read": "doctor", "to": "items.rows", "from": "items"},
        {"on": "reload.pressed", "refresh": True},
    ],
}
