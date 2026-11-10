"""モジュール › 概要：名前・型・リポジトリなど。"""

SCREEN = {
    "root": "page",
    "window": {"title": "ECOBuild", "width": 760, "height": 560},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["nav", "title", "info"]},
        {"id": "nav", "screen": "menu", "args": {"current": "overview"}},
        {"id": "title", "part": "note", "props": {"text": "概要", "heading": True}},
        {"id": "info", "part": "facts", "props": {
            "items": [
                {"key": "name", "label": "名前"}, {"key": "type", "label": "型"}, {"key": "root", "label": "場所"},
                {"key": "repository", "label": "リポジトリ"}, {"key": "private", "label": "公開"},
                {"key": "default_base", "label": "作成元のブランチ"},
            ],
            "labels": {"private": {"true": "非公開", "false": "公開"}},
        }},
    ],
    "bindings": [
        {"read": "module show", "to": "info.data"},
    ],
}
