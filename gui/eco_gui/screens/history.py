"""モジュール › 履歴：コミットの一覧と、選んだコミットの中身。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "履歴", "width": 900, "height": 680},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["nav", "title", "log", "detail"]},
        {"id": "nav", "screen": "menu", "args": {"current": "history", "module": {"arg": "module"}}},
        {"id": "title", "part": "note", "props": {"text": "履歴", "heading": True}},
        {"id": "log", "part": "table", "props": {
            "columns": [{"key": "date", "label": "日時"}, {"key": "author", "label": "だれが"}, {"key": "subject", "label": "何を"}],
            "key": "sha", "actions": [{"name": "show", "label": "見る"}], "empty_text": "コミットはまだありません。",
        }},
        {"id": "detail", "part": "text-view", "props": {"empty_text": "「見る」で、コミットの中身が出ます。"}},
    ],
    "bindings": [
        {"read": "log", "args": {"module": {"arg": "module"}, "count": 30}, "to": "log.rows"},
        {"on": "log.action", "when": {"action": "show"}, "set": {"commit": {"payload": "id"}}},
        {"read": "show", "args": {"module": {"arg": "module"}, "commit": {"value": "commit"}}, "to": "detail.text"},
    ],
}
