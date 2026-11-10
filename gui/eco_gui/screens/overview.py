"""モジュール › 概要：名前・型・リポジトリなど。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "ECOBuild", "width": 760, "height": 560},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["nav", "title", "info", "open_here", "spaces_title", "spaces"]},
        {"id": "nav", "screen": "menu", "args": {"current": "overview", "module": {"arg": "module"}}},
        {"id": "title", "part": "note", "props": {"text": "概要", "heading": True}},
        {"id": "info", "part": "facts", "props": {
            "items": [
                {"key": "name", "label": "名前"}, {"key": "type", "label": "型"}, {"key": "root", "label": "場所"},
                {"key": "repository", "label": "リポジトリ"}, {"key": "private", "label": "公開"},
                {"key": "default_base", "label": "作成元のブランチ"},
            ],
            "labels": {"private": {"true": "非公開", "false": "公開"}},
        }},
        {"id": "open_here", "part": "button", "props": {"label": "この場所の作業空間を開く"}},
        {"id": "spaces_title", "part": "note", "props": {"text": "タスクの作業空間"}},
        {"id": "spaces", "part": "table", "props": {
            "columns": [{"key": "task", "label": "タスク"}, {"key": "branch", "label": "ブランチ"}, {"key": "path", "label": "場所"}],
            "key": "path", "actions": [{"name": "open", "label": "開く"}],
            "empty_text": "タスクの作業空間はありません。",
        }},
    ],
    "bindings": [
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "info.data"},
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "spaces.rows", "from": "workspaces"},
        # 作業空間の窓を開く（場所ごとに1つ）
        {"on": "open_here.pressed", "open": "workspace", "args": {"module": {"arg": "module"}}},
        {"on": "spaces.action", "when": {"action": "open"}, "open": "workspace", "args": {"module": {"payload": "id"}}},
    ],
}
