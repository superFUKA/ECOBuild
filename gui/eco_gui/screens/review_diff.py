"""提出の差分：タスクの提出で変わるところ（ecobuild task diff <番号>）。提出の詳細から、窓の中に重ねて開く。"""

ARGS = {"module": ".", "task": ""}  # モジュールのフォルダー・タスクの番号

SCREEN = {
    "root": "page",
    "window": {"title": "提出の差分", "width": 1000, "height": 760},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["head", "diff"]},
        {"id": "head", "layout": "row", "look": "bar", "children": ["title", "close"]},
        {"id": "title", "part": "note", "props": {"prefix": "差分：#", "text": {"arg": "task"}, "heading": True}},
        {"id": "close", "part": "button", "props": {"label": "閉じる"}},
        {"id": "diff", "part": "text-view", "props": {"empty_text": "差分はありません。"}},
    ],
    "bindings": [
        {"read": "task diff", "args": {"module": {"arg": "module"}, "task": {"arg": "task"}}, "require": ["task"], "to": "diff.text"},
        {"on": "close.pressed", "close": True},
    ],
}
