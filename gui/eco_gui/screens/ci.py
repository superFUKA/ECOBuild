"""モジュール › CI：設定と、最近の実行。"""

ARGS = {"module": "."}  # モジュールのフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "CI", "width": 760, "height": 560},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["nav", "head", "config", "runs"]},
        {"id": "nav", "screen": "menu", "args": {"current": "ci", "module": {"arg": "module"}}},
        {"id": "head", "layout": "row", "children": ["title", "run", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "CI", "heading": True}},
        {"id": "run", "part": "button", "props": {"label": "流す", "hint": "作成元のブランチで CI を流す"}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "config", "part": "facts", "props": {
            "items": [{"key": "path", "label": "設定のファイル"}, {"key": "exists", "label": "設定"},
                      {"key": "os", "label": "OS"}, {"key": "configurations", "label": "構成"}],
            "labels": {"exists": {"true": "あり", "false": "まだありません"}},
        }},
        {"id": "runs", "part": "table", "props": {
            "columns": [{"key": "id", "label": "実行"}, {"key": "branch", "label": "ブランチ"}, {"key": "status", "label": "状態"},
                        {"key": "conclusion", "label": "結果"}, {"key": "message", "label": "コミット"}],
            "key": "id",
            "labels": {"status": {"completed": "終わった", "in_progress": "実行中", "queued": "待っている"},
                       "conclusion": {"success": "成功", "failure": "失敗", "cancelled": "取り消し"}},
            "empty_text": "CI の実行はまだありません。",
        }},
    ],
    "bindings": [
        {"read": "ci show", "args": {"module": {"arg": "module"}}, "to": "config.data"},
        {"read": "ci status", "args": {"module": {"arg": "module"}}, "to": "runs.rows"},
        {"on": "run.pressed", "run": "ci run", "args": {"module": {"arg": "module"}}},
        {"on": "reload.pressed", "refresh": True},
    ],
}
