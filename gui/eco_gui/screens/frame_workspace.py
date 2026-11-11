"""モジュール › 作業空間：左のメニュー、作業空間のタブ、選んだ作業空間の中身（作業空間の画面 workspace を、そのまま中に置く）。

どの作業空間かは画面の引数 space。タブを選ぶと、同じ窓で space を変えて開き直す。"""

ARGS = {"module": ".", "space": "", "closed": []}  # モジュールのフォルダー・出す作業空間のフォルダー・閉じたタブ

SCREEN = {
    "root": "page",
    "window": {"title": "ECOBuild", "width": 1280, "height": 860, "refresh": {"focus": True, "every": 180}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "nav", "screen": "menu", "args": {"current": "frame-workspaces", "module": {"arg": "module"}}},
        {"id": "main", "layout": "column", "look": "frame-main", "children": ["bar", "ws"]},
        {"id": "bar", "screen": "frame-bar", "args": {"module": {"arg": "module"}, "space": {"arg": "space"}, "closed": {"arg": "closed"}}},
        {"id": "ws", "screen": "workspace", "args": {"module": {"arg": "space"}}},
    ],
    "bindings": [],
}
