"""モジュールの窓のメニュー（どの画面にも置く）。選ぶと、同じ窓でその画面に切り替わる。"""

ARGS = {"current": ""}

SCREEN = {
    "root": "menu",
    "nodes": [
        {"id": "menu", "part": "menu", "props": {"current": {"arg": "current"}, "items": [
            {"id": "overview", "label": "概要"},
            {"id": "tasks", "label": "タスク"},
            {"id": "members", "label": "メンバー"},
            {"id": "pipelines", "label": "パイプライン"},
            {"id": "ci", "label": "CI"},
        ]}},
    ],
    "bindings": [
        {"on": "menu.selected", "open": {"payload": "id"}, "here": True},
    ],
}
