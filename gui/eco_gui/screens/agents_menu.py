"""モジュール › エージェント の中のメニュー（登録・スキル・共通の文・このPCのプリセット）。選ぶと、同じ窓で切り替わる。"""

ARGS = {"current": "", "module": "."}

SCREEN = {
    "root": "menu",
    "nodes": [
        {"id": "menu", "part": "menu", "props": {"current": {"arg": "current"}, "items": [
            {"id": "agents", "label": "登録（役）"},
            {"id": "agent-skills", "label": "スキル"},
            {"id": "agent-rules", "label": "全エージェント共通の文"},
            {"id": "agent-presets", "label": "このPCのプリセット"},
        ]}},
    ],
    "bindings": [
        {"on": "menu.selected", "open": {"payload": "id"}, "args": {"module": {"arg": "module"}}, "here": True},
    ],
}
