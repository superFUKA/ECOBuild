"""モジュール › タスク：開いているタスクの一覧。"""

SCREEN = {
    "root": "page",
    "window": {"title": "タスク", "width": 760, "height": 560},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["nav", "head", "tasks"]},
        {"id": "nav", "screen": "menu", "args": {"current": "tasks"}},
        {"id": "head", "layout": "row", "children": ["title", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "タスク", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "読み直す"}},
        {"id": "tasks", "part": "table", "props": {
            "columns": [{"key": "number", "label": "#"}, {"key": "title", "label": "題名"}, {"key": "stage", "label": "段階"},
                        {"key": "assignees", "label": "担当"}],
            "key": "number",
            "labels": {"stage": {"planned": "計画中", "todo": "未着手", "in_progress": "作業中", "in_review": "レビュー待ち", "done": "完了"}},
            "empty_text": "開いているタスクはありません。",
        }},
    ],
    "bindings": [
        {"read": "task list", "to": "tasks.rows"},
        {"on": "reload.pressed", "refresh": True},
    ],
}
