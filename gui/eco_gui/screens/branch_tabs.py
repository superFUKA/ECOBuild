"""「ブランチ」の上のタブ（ブランチ・提出・履歴）。ブランチのどの画面にも置く。選ぶと、同じ窓でその画面に切り替わる。"""

ARGS = {"current": "", "module": "."}

SCREEN = {
    "root": "tabs",
    "nodes": [
        {"id": "tabs", "part": "section-tabs", "props": {"current": {"arg": "current"}, "items": [
            {"id": "branches", "label": "ブランチ"},
            {"id": "submissions", "label": "提出"},
            {"id": "history", "label": "履歴"},
        ]}},
    ],
    "bindings": [
        {"on": "tabs.selected", "open": {"payload": "id"}, "args": {"module": {"arg": "module"}}, "here": True},
    ],
}
