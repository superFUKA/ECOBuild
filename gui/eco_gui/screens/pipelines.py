"""モジュール › パイプライン：決まった手順（生成・ビルド・試験など）をまとめて流す。"""

SCREEN = {
    "root": "page",
    "window": {"title": "パイプライン", "width": 760, "height": 560},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["nav", "title", "list", "form"]},
        {"id": "nav", "screen": "menu", "args": {"current": "pipelines"}},
        {"id": "title", "part": "note", "props": {"text": "パイプライン", "heading": True}},
        {"id": "list", "part": "table", "props": {
            "columns": [{"key": "name", "label": "名前"}, {"key": "steps", "label": "手順"}, {"key": "tests", "label": "流す試験"}],
            "key": "name",
            "actions": [{"name": "run", "label": "流す"}, {"name": "remove", "label": "消す"}],
            "empty_text": "パイプラインはまだありません。",
        }},
        {"id": "form", "layout": "row", "children": ["name", "steps", "add"]},
        {"id": "name", "part": "text-input", "props": {"title": "名前", "placeholder": "例：check"}},
        {"id": "steps", "part": "text-input", "props": {"title": "手順（, で区切る）", "placeholder": "generated,build,test"}},
        {"id": "add", "part": "button", "props": {"label": "＋ 足す", "primary": True}},
    ],
    "bindings": [
        {"read": "pipeline list", "to": "list.rows", "from": "pipelines"},
        {"on": "name.changed", "set": {"name": {"payload": "text"}}},
        {"on": "steps.changed", "set": {"steps": {"payload": "text"}}},
        {"on": "add.pressed", "run": "pipeline add", "args": {"name": {"value": "name"}, "steps": {"value": "steps"}}},
        # 行のボタン：どれが押されたかで、呼ぶコマンドを分ける
        {"on": "list.action", "when": {"action": "run"}, "run": "pipeline run", "args": {"name": {"payload": "id"}}},
        {"on": "list.action", "when": {"action": "remove"}, "run": "pipeline remove", "args": {"name": {"payload": "id"}}},
    ],
}
