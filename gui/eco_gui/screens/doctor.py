"""環境チェック：ECOBuild を使うのに要る道具が、この PC にそろっているか（確認済み・要対応・任意）。"""

SCREEN = {
    "root": "page",
    "window": {"title": "環境チェック", "width": 900, "height": 640},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["head", "items"]},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "環境チェック", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "チェックする"}},
        {"id": "items", "part": "hub-doctor"},
    ],
    "bindings": [
        {"read": "doctor", "to": "items.items", "from": "items"},
        {"on": "reload.pressed", "refresh": True},
    ],
}
