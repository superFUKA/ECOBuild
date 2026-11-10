"""ファイルの記録：このファイルを変えたコミットと、行ごとの記録（どの行を、どのコミットで変えたか）。"""

ARGS = {"module": ".", "path": ""}  # モジュールのフォルダー・見るファイル

SCREEN = {
    "root": "page",
    "window": {"title": "ファイルの記録", "width": 980, "height": 760},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["title", "log_title", "log", "lines_title", "lines"]},
        {"id": "title", "part": "note", "props": {"text": {"arg": "path"}, "prefix": "ファイルの記録：", "heading": True}},
        {"id": "log_title", "part": "note", "props": {"text": "このファイルを変えたコミット"}},
        {"id": "log", "part": "table", "props": {
            "columns": [{"key": "date", "label": "日時"}, {"key": "author", "label": "だれが"}, {"key": "subject", "label": "何を"}],
            "key": "sha", "empty_text": "コミットはまだありません。",
        }},
        {"id": "lines_title", "part": "note", "props": {"text": "行ごとの記録"}},
        {"id": "lines", "part": "text-view", "props": {"empty_text": "まだコミットしていないファイルには、記録がありません。"}},
    ],
    "bindings": [
        {"read": "log", "args": {"module": {"arg": "module"}, "paths": [{"arg": "path"}], "count": 30}, "to": "log.rows"},
        {"read": "blame", "args": {"module": {"arg": "module"}, "path": {"arg": "path"}}, "to": "lines.text"},
    ],
}
