"""モジュールの窓の左のメニュー（どの画面にも置く）。選ぶと、同じ窓でそのまとまりの最初の画面に切り替わる。

まとまりの中の画面は、ページの上のタブで切り替える（モジュール：mod-tabs、タスク管理：task-head、ブランチ：branch-tabs、設定：設定の画面のタブ）。
"""

ARGS = {"current": "", "module": "."}

SCREEN = {
    "root": "menu",
    "nodes": [
        {"id": "menu", "part": "menu", "props": {"current": {"arg": "current"}, "items": [
            {"id": "overview", "label": "モジュール", "icon": "module"},
            {"id": "frame-workspaces", "label": "作業空間", "icon": "folder"},
            {"id": "board", "label": "タスク管理", "icon": "tasks"},  # 最初はボード（前の GUI と同じ）
            {"id": "branches", "label": "ブランチ", "icon": "branch"},
            {"id": "settings", "label": "設定", "icon": "settings", "bottom": True},
            {"id": "help", "label": "ヘルプ", "icon": "help", "bottom": True},
        ]}},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "menu.title", "from": "name"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "from": "name", "title": "{} — ECOBuild"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "menu.account"},
        {"on": "menu.selected", "open": {"payload": "id"}, "args": {"module": {"arg": "module"}}, "here": True},
        {"on": "menu.account", "open": "settings", "args": {"module": {"arg": "module"}}, "here": True},
    ],
}
