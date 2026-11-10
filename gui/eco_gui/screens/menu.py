"""モジュールの窓の左のメニュー（どの画面にも置く）。選ぶと、同じ窓でその画面に切り替わる。"""

ARGS = {"current": "", "module": "."}

SCREEN = {
    "root": "menu",
    "nodes": [
        {"id": "menu", "part": "menu", "props": {"current": {"arg": "current"}, "items": [
            {"id": "overview", "label": "概要", "icon": "module", "group": "モジュール"},
            {"id": "files", "label": "ファイル", "icon": "folder", "group": "モジュール"},
            {"id": "members", "label": "メンバー", "icon": "members", "group": "モジュール"},
            {"id": "pipelines", "label": "パイプライン", "icon": "flow", "group": "モジュール"},
            {"id": "ci", "label": "CI", "icon": "ci", "group": "モジュール"},
            {"id": "agents", "label": "エージェント", "icon": "agent", "group": "モジュール"},
            {"id": "tasks", "label": "タスク", "icon": "tasks", "group": "タスク管理"},
            {"id": "board", "label": "ボード", "icon": "board", "group": "タスク管理"},
            {"id": "schedule", "label": "日程", "icon": "calendar", "group": "タスク管理"},
            {"id": "submissions", "label": "提出", "icon": "submit", "group": "タスク管理"},
            {"id": "branches", "label": "ブランチ", "icon": "branch", "group": "ブランチ"},
            {"id": "history", "label": "履歴", "icon": "history", "group": "ブランチ"},
            {"id": "settings", "label": "設定", "icon": "settings", "bottom": True},
            {"id": "container", "label": "コンテナ", "icon": "container", "bottom": True},
            {"id": "help", "label": "ヘルプ", "icon": "help", "bottom": True},
        ]}},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "menu.title", "from": "name"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "menu.account"},
        {"on": "menu.selected", "open": {"payload": "id"}, "args": {"module": {"arg": "module"}}, "here": True},
        {"on": "menu.account", "open": "settings", "args": {"module": {"arg": "module"}}, "here": True},
    ],
}
