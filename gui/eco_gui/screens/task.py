"""モジュール › タスク管理 › タスクの詳細（1つのタスクを、窓いっぱいに）。中身は、一覧の右に出す詳細（task-pane）と同じ。"""

ARGS = {"module": ".", "issue": 0}  # モジュールのフォルダーと、タスクの番号

SCREEN = {
    "root": "page",
    "window": {"title": "タスクの詳細", "width": 1280, "height": 820, "refresh": {"focus": True, "every": 180}},
    "nodes": [
        {"id": "page", "layout": "row", "look": "shell", "children": ["nav", "main"]},
        {"id": "main", "layout": "column", "look": "tk-page", "children": ["top", "scroll"]},
        {"id": "nav", "screen": "menu", "args": {"current": "tasks", "module": {"arg": "module"}}},
        {"id": "top", "layout": "row", "look": "tk-top", "children": ["title", "back", "reload"]},
        {"id": "title", "part": "note", "props": {"text": "タスク管理", "heading": True}},
        {"id": "back", "part": "button", "props": {"label": "‹ 一覧へ"}},
        {"id": "reload", "part": "button", "props": {"label": "更新"}},
        {"id": "scroll", "layout": "column", "look": "tk-single", "children": ["detail"]},
        {"id": "detail", "screen": "task-pane", "args": {"module": {"arg": "module"}, "number": {"arg": "issue"}, "look": "tk-part", "closable": False}},
    ],
    "bindings": [
        {"on": "reload.pressed", "refresh": True},
        {"on": "back.pressed", "open": "tasks", "args": {"module": {"arg": "module"}}, "here": True},
        {"on": "detail.selected", "open": "task", "args": {"module": {"arg": "module"}, "issue": {"payload": "id"}}, "here": True},  # つながりのタスクへ
    ],
}
