"""「モジュール」の上のタブ（ホーム・Project・依存先・メンバー・パイプライン・CI・エージェント）。モジュールのどの画面にも置く。

選ぶと、同じ窓でその画面に切り替わる。Project・依存先は、C++ のモジュールでだけ出す。
"""

ARGS = {"current": "", "module": "."}

SCREEN = {
    "root": "tabs",
    "nodes": [
        {"id": "tabs", "part": "section-tabs", "props": {"current": {"arg": "current"}, "items": [
            {"id": "overview", "label": "ホーム"},
            {"id": "cpp", "label": "Project", "only": "cpp"},
            {"id": "cpp-deps", "label": "依存先", "only": "cpp"},
            {"id": "members", "label": "メンバー"},
            {"id": "pipelines", "label": "パイプライン"},
            {"id": "ci", "label": "CI"},
            {"id": "agents", "label": "エージェント"},
        ]}},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "tabs.kind", "from": "type"},
        {"on": "tabs.selected", "open": {"payload": "id"}, "args": {"module": {"arg": "module"}}, "here": True},
    ],
}
