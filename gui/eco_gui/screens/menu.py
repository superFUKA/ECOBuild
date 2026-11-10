"""モジュールの窓のメニュー（どの画面にも置く）。選ぶと、同じ窓でその画面に切り替わる。"""

ARGS = {"current": "", "module": "."}

SCREEN = {
    "root": "menu",
    "nodes": [
        {"id": "menu", "part": "menu", "props": {"current": {"arg": "current"}, "items": [
            {"id": "overview", "label": "概要"},
            {"id": "files", "label": "ファイル"},
            {"id": "tasks", "label": "タスク"},
            {"id": "board", "label": "ボード"},
            {"id": "schedule", "label": "日程"},
            {"id": "submissions", "label": "提出"},
            {"id": "branches", "label": "ブランチ"},
            {"id": "history", "label": "履歴"},
            {"id": "members", "label": "メンバー"},
            {"id": "pipelines", "label": "パイプライン"},
            {"id": "ci", "label": "CI"},
            {"id": "agents", "label": "エージェント"},
            {"id": "settings", "label": "設定"},
            {"id": "container", "label": "コンテナ"},
            {"id": "help", "label": "ヘルプ"},
        ]}},
    ],
    "bindings": [
        {"on": "menu.selected", "open": {"payload": "id"}, "args": {"module": {"arg": "module"}}, "here": True},
    ],
}
