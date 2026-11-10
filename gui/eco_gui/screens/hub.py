"""ハブ：この PC にあるモジュールの一覧。選ぶと、そのモジュールの窓を開く。"""

SCREEN = {
    "root": "page",
    "window": {"title": "ECOBuild", "width": 820, "height": 560},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["head", "modules"]},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "モジュール", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "modules", "part": "table", "props": {
            "columns": [{"key": "path", "label": "場所"}, {"key": "type", "label": "型"}, {"key": "branch", "label": "ブランチ"}],
            "key": "path",
            "actions": [{"name": "open", "label": "開く"}],
            "empty_text": "モジュールはまだありません。",
        }},
    ],
    "bindings": [
        {"read": "workspace list", "to": "modules.rows", "from": "modules"},
        {"on": "reload.pressed", "refresh": True},
        # 選んだモジュールの窓を開く（モジュールごとに1つ。開いていれば前に出る）
        {"on": "modules.action", "when": {"action": "open"}, "open": "overview", "args": {"module": {"payload": "id"}}},
    ],
}
